from collections import Counter
import re

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import Evidence, RetrievalRequest, RetrievalResponse
from app.config import Settings
from app.db.models import Chunk, ChunkEmbedding, Collection, Document, LibraryBook
from app.embeddings.base import EmbeddingError
from app.embeddings.provider import provider
from app.security import public_source_url


def rrf(pools, k=60, weights=None):
    weights = weights or [1.0] * len(pools)
    if len(weights) != len(pools):
        raise ValueError("RRF_WEIGHT_COUNT")
    scores: dict[str, float] = {}
    for pool, weight in zip(pools, weights, strict=True):
        seen = set()
        for rank, key in enumerate(pool, 1):
            if key not in seen:
                scores[key] = scores.get(key, 0) + weight / (k + rank)
                seen.add(key)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def retrieve(db: Session, request: RetrievalRequest, settings: Settings, *, subject=None):
    shared = set(settings.allowed_collections) - set(settings.private_collections)
    private = set(settings.private_collections)
    if not set(request.collection_ids) <= shared | private:
        raise PermissionError("COLLECTION_NOT_ALLOWED")
    if set(request.collection_ids) & private and subject is None:
        raise PermissionError("PRIVATE_SCOPE_REQUIRED")
    if (
        set(request.collection_ids) & private
        and settings.embedding_provider == "openai"
        and request.mode != "keyword"
    ):
        raise PermissionError("PRIVATE_LOCAL_EMBEDDINGS_REQUIRED")
    public_access = and_(Collection.slug.in_(shared), Collection.visibility == "CURATED_SHARED")
    private_access = (
        and_(
            Collection.slug.in_(private),
            Collection.visibility == "PRIVATE",
            LibraryBook.visibility == "PRIVATE",
            LibraryBook.owner_id == subject,
            Document.book_id.is_not(None),
        )
        if subject
        else false()
    )
    conditions = [
        Collection.slug.in_(request.collection_ids),
        or_(public_access, private_access),
        Document.approved.is_(True),
        Document.status != "DELETED",
        Chunk.revision == Document.active_revision,
        Chunk.collection_id == Document.collection_id,
        or_(
            Document.book_id.is_(None),
            and_(
                LibraryBook.approved.is_(True),
                LibraryBook.status.in_(["INDEXED", "PARTIALLY_INDEXED"]),
                or_(
                    and_(LibraryBook.visibility == "CURATED_SHARED", public_access), private_access
                ),
                LibraryBook.collection_id == Document.collection_id,
                LibraryBook.active_generation == Document.book_generation,
            ),
        ),
    ]
    filters = request.filters
    for values, filter_column in (
        (filters.subject, Document.subject),
        (filters.course, Document.course_code),
        (filters.document_ids, Document.id),
        (filters.publication_year, Document.publication_year),
        (filters.title, Document.title),
        (filters.author, Document.author),
        (filters.source_type, Document.content_type),
    ):
        if values:
            conditions.append(filter_column.in_(values))
    base = (
        select(Chunk, Document, Collection.slug)
        .join(Document, Chunk.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .outerjoin(LibraryBook, Document.book_id == LibraryBook.id)
        .where(*conditions)
    )
    embedder = provider(settings) if request.mode != "keyword" else None
    if request.mode == "semantic" and not embedder:
        raise EmbeddingError("EMBEDDING_DISABLED")
    mode = request.mode if embedder or request.mode == "keyword" else "keyword"
    fallback_reason = "EMBEDDING_DISABLED" if mode != request.mode else None
    pools = []
    rows_by_id: dict[str, tuple[Chunk, Document, str, float]] = {}
    scores_by_id: dict[str, float] = {}
    broad_keyword = False
    # Overfetch a bounded pool so repeated copies cannot fill the evidence list.
    # Score IDs first; fetching full text/metadata before the top-N sort makes
    # exact vector search unnecessarily expensive on a full-length library.
    limit = min(300, max(request.top_k * 20, 100))
    canonical_text: dict[str, str] = {}

    def hydrate(ranks):
        if not ranks:
            return []
        found = {
            row[0].id: row
            for row in db.execute(base.where(Chunk.id.in_([r[0] for r in ranks]))).all()
        }
        return [(*found[key], score) for key, score in ranks if key in found]

    def add_pool(rows):
        pool, seen = [], set()
        for row in rows:
            identifier = str(row[0].id)
            key = canonical_text.setdefault(row[0].text, identifier)
            rows_by_id.setdefault(key, row)
            scores_by_id.setdefault(key, float(row[3]))
            if key not in seen:
                pool.append(key)
                seen.add(key)
        pools.append(pool)

    if mode in {"keyword", "hybrid"}:
        previous_nestloop = db.scalar(select(func.current_setting("enable_nestloop")))
        db.execute(select(func.set_config("enable_nestloop", "off", True)))
        query = func.websearch_to_tsquery("english", request.query)
        score = func.ts_rank_cd(Chunk.search_vector, query)
        rows = db.execute(
            base.with_only_columns(Chunk.id, score.label("score"))
            .where(Chunk.search_vector.op("@@")(query))
            .order_by(score.desc(), Chunk.id)
            .limit(limit)
        ).all()
        if not rows:
            # Natural questions often contain words absent from a passage. Broaden
            # only to a bounded indexed disjunction, never to unrelated documents.
            terms = re.findall(r"[^\W_]{2,}", request.query, flags=re.UNICODE)[:32]
            if terms:
                broad_keyword = True
                broad_query = func.websearch_to_tsquery("english", " OR ".join(terms))
                broad_score = func.ts_rank_cd(Chunk.search_vector, broad_query)
                rows = db.execute(
                    base.with_only_columns(Chunk.id, broad_score.label("score"))
                    .where(Chunk.search_vector.op("@@")(broad_query))
                    .order_by(broad_score.desc(), Chunk.id)
                    .limit(limit)
                ).all()
        db.execute(select(func.set_config("enable_nestloop", previous_nestloop, True)))
        add_pool(hydrate(rows))
    if mode in {"semantic", "hybrid"}:
        assert embedder is not None
        try:
            vector = embedder.embed_query(request.query)
            identity = embedder.identity
        except (ValueError, KeyError, IndexError) as exc:
            if mode != "hybrid":
                raise EmbeddingError("EMBEDDING_UNAVAILABLE") from None
            mode = "keyword"
            fallback_reason = (
                str(exc) if isinstance(exc, EmbeddingError) else "EMBEDDING_UNAVAILABLE"
            )
        else:
            column = (
                ChunkEmbedding.embedding_1024
                if embedder.dimensions == 1024
                else ChunkEmbedding.embedding_1536
            )
            distance = column.cosine_distance(vector)
            # Correlated ownership/generation joins can severely underestimate
            # cardinality and choose hundreds of thousands of PK lookups. Use a
            # local hash/merge-join plan for the narrow exact-distance ranking;
            # restore the caller's setting before bounded metadata hydration.
            previous_nestloop = db.scalar(select(func.current_setting("enable_nestloop")))
            db.execute(select(func.set_config("enable_nestloop", "off", True)))
            ranks = list(
                db.execute(
                    base.join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
                    .with_only_columns(Chunk.id, (1 - distance).label("score"))
                    .where(
                        column.is_not(None),
                        ChunkEmbedding.identity == identity,
                        ChunkEmbedding.dimensions == embedder.dimensions,
                    )
                    .order_by(distance, Chunk.id)
                    .limit(limit)
                ).all()
            )
            if embedder.dimensions == 1536 and embedder.legacy_identity:
                legacy_distance = Chunk.embedding.cosine_distance(vector)
                # Legacy raw OpenAI vectors are usable only for their exact original
                # endpoint/model, and only when a new matching row is absent.
                exists = (
                    select(ChunkEmbedding.chunk_id)
                    .where(ChunkEmbedding.chunk_id == Chunk.id, ChunkEmbedding.identity == identity)
                    .exists()
                )
                ranks += list(
                    db.execute(
                        base.with_only_columns(Chunk.id, (1 - legacy_distance).label("score"))
                        .where(
                            Chunk.embedding.is_not(None),
                            Chunk.embedding_identity == embedder.legacy_identity,
                            ~exists,
                        )
                        .order_by(legacy_distance, Chunk.id)
                        .limit(limit)
                    ).all()
                )
                ranks = sorted(ranks, key=lambda row: (-float(row[1]), str(row[0])))[:limit]
            # On a SQL error the transaction is aborted; rollback also resets
            # SET LOCAL. Do not mask that error by trying another SQL statement.
            db.execute(select(func.set_config("enable_nestloop", previous_nestloop, True)))
            add_pool(hydrate(ranks))
    # An OR-broadened query has weaker lexical agreement than the original FTS
    # query. Keep those candidates but reduce their influence in hybrid fusion.
    ranked = (
        rrf(pools, weights=[0.5, 1.0] if broad_keyword else None)
        if mode == "hybrid"
        else [(key, scores_by_id[key]) for key in pools[0]]
    )
    results: list[Evidence] = []
    counts: Counter = Counter()
    for key, score_value in ranked:
        chunk, doc, slug, _ = rows_by_id[key]
        db.refresh(doc)
        book_record = (
            db.get(LibraryBook, doc.book_id, populate_existing=True) if doc.book_id else None
        )
        if not doc.approved or doc.status == "DELETED" or chunk.revision != doc.active_revision:
            continue
        if doc.book_id and (
            not book_record
            or not book_record.approved
            or book_record.status not in {"INDEXED", "PARTIALLY_INDEXED"}
            or book_record.active_generation != doc.book_generation
            or (book_record.visibility == "PRIVATE" and str(book_record.owner_id) != subject)
        ):
            continue
        diversity_key = doc.book_id or doc.id
        if counts[diversity_key] >= 3:
            continue
        counts[diversity_key] += 1
        locators = []
        if chunk.page_start is not None:
            locators.append(
                f"{'PDF page' if doc.book_id and doc.content_type == '.pdf' else 'Page'} {chunk.page_start}"
                + (f"–{chunk.page_end}" if chunk.page_end != chunk.page_start else "")
            )
        if chunk.heading_path:
            locators.append(chunk.heading_path)
        if chunk.start_ms is not None:
            locators.append(f"{chunk.start_ms}–{chunk.end_ms} ms")
        results.append(
            Evidence(
                chunk_id=chunk.id,
                document_id=doc.id,
                collection_id=slug,
                title=doc.title,
                book_id=doc.book_id,
                author=doc.author,
                edition=chunk.source_metadata.get("edition"),
                chapter=chunk.heading_path if doc.book_id else None,
                extraction=chunk.source_metadata.get("extraction"),
                review_required=chunk.source_metadata.get("extraction")
                in {"LOCAL_TESSERACT_OCR", "VISUAL_DESCRIPTION", "VISUALLY_REVIEWED_TRANSCRIPTION"}
                or bool(
                    chunk.source_metadata.get("formula_review_required")
                    and re.search(
                        r"\b(quant|quantitative|statistics|mathematics|accounting|calculus|physics|compilation)\b",
                        doc.title,
                        re.I,
                    )
                ),
                coverage_note=" ".join(
                    filter(
                        None,
                        [
                            "Some image-only pages remain unindexed; consult original PDF."
                            if book_record and book_record.status == "PARTIALLY_INDEXED"
                            else None,
                            chunk.source_metadata.get("source_notice"),
                        ],
                    )
                )
                or None,
                course_code=doc.course_code,
                institution=doc.institution,
                locator=" / ".join(locators) or None,
                locator_missing=not bool(locators),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                source_url=public_source_url(doc.source_url),
                revision=chunk.revision,
                text=chunk.text,
                snippet=chunk.text[:240],
                rank=len(results) + 1,
                score=score_value,
            )
        )
        if len(results) == request.top_k:
            break
    return RetrievalResponse(
        retrieval_mode_used=mode,
        fallback_reason=fallback_reason,
        score_semantics={
            "keyword": "PostgreSQL ts_rank_cd; not a probability",
            "semantic": "cosine similarity; not a probability",
            "hybrid": "RRF sum(weight/(60+rank)); broadened keyword weight=0.5, otherwise weights=1; not a probability",
        }[mode],
        results=results,
    )
