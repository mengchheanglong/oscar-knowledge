from collections import Counter
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import Evidence, RetrievalRequest, RetrievalResponse
from app.config import Settings
from app.db.models import Chunk, ChunkEmbedding, Collection, Document
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


def retrieve(db: Session, request: RetrievalRequest, settings: Settings):
    if not set(request.collection_ids) <= set(settings.allowed_collections):
        raise PermissionError("COLLECTION_NOT_ALLOWED")
    conditions = [
        Collection.slug.in_(request.collection_ids),
        Collection.visibility == "CURATED_SHARED",
        Document.approved.is_(True),
        Document.status != "DELETED",
        Chunk.revision == Document.active_revision,
        Chunk.collection_id == Document.collection_id,
    ]
    filters = request.filters
    for values, filter_column in (
        (filters.subject, Document.subject),
        (filters.course, Document.course_code),
        (filters.document_ids, Document.id),
        (filters.publication_year, Document.publication_year),
    ):
        if values:
            conditions.append(filter_column.in_(values))
    base = (
        select(Chunk, Document, Collection.slug)
        .join(Document, Chunk.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .where(*conditions)
    )
    embedder = provider(settings) if request.mode != "keyword" else None
    if request.mode == "semantic" and not embedder:
        raise EmbeddingError("EMBEDDING_DISABLED")
    mode = request.mode if embedder or request.mode == "keyword" else "keyword"
    fallback_reason = "EMBEDDING_DISABLED" if mode != request.mode else None
    pools = []
    rows_by_id = {}
    scores_by_id = {}
    broad_keyword = False
    limit = min(100, max(request.top_k * 5, 30))
    if mode in {"keyword", "hybrid"}:
        query = func.websearch_to_tsquery("english", request.query)
        score = func.ts_rank_cd(Chunk.search_vector, query)
        rows = db.execute(
            base.add_columns(score.label("score"))
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
                    base.add_columns(broad_score.label("score"))
                    .where(Chunk.search_vector.op("@@")(broad_query))
                    .order_by(broad_score.desc(), Chunk.id)
                    .limit(limit)
                ).all()
        pools.append([str(row[0].id) for row in rows])
        for row in rows:
            rows_by_id[str(row[0].id)] = row
            scores_by_id[str(row[0].id)] = float(row[3])
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
            rows = list(
                db.execute(
                    base.join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
                    .add_columns((1 - distance).label("score"))
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
                rows += list(
                    db.execute(
                        base.add_columns((1 - legacy_distance).label("score"))
                        .where(
                            Chunk.embedding.is_not(None),
                            Chunk.embedding_identity == embedder.legacy_identity,
                            ~exists,
                        )
                        .order_by(legacy_distance, Chunk.id)
                        .limit(limit)
                    ).all()
                )
                rows = sorted(rows, key=lambda row: (-float(row[3]), str(row[0].id)))[:limit]
            pools.append([str(row[0].id) for row in rows])
            for row in rows:
                rows_by_id[str(row[0].id)] = row
                if mode == "semantic":
                    scores_by_id[str(row[0].id)] = float(row[3])
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
        if counts[doc.id] >= 3:
            continue
        counts[doc.id] += 1
        locators = []
        if chunk.page_start is not None:
            locators.append(
                f"Page {chunk.page_start}"
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
