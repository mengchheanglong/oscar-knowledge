from collections import Counter
from math import log
import re

from sqlalchemy import func, or_, select, text as sql_text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.api.schemas import Evidence, RetrievalRequest, RetrievalResponse
from app.config import Settings
from app.db.models import Chunk, ChunkEmbedding, Collection, Document, LibraryBook
from app.embeddings.base import EmbeddingError
from app.embeddings.provider import provider
from app.library.access import can_read_private_book
from app.library.eligibility import current_source_conditions
from app.security import public_source_url
from app.retrieval.query_terms import lexical_alternatives

ENGLISH_STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "would",
    "you",
    "your",
    "yours",
}


def rrf(pools, k=60, weights=None, bonus_by_id=None):
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
    if bonus_by_id:
        for key, bonus in bonus_by_id.items():
            if key in scores:
                scores[key] += bonus
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def named_source_topic(query: str, titles: list[str]) -> tuple[list[str], str]:
    """Discover named titles from eligible candidates, never from a global catalog.

    Remove a matched title from the lexical topic so its repeated words do not
    drown out the requested concept. This is a soft additional search, not an
    authorization rule or a claim that the remaining library is irrelevant.
    """
    normalized = " ".join(re.findall(r"[^\W_]+", query.lower()))
    matched = []
    topic = f" {normalized} "
    for title in sorted(set(titles)):
        name = re.split(r"[:—]", title.lower(), maxsplit=1)[0]
        words = re.findall(r"[^\W_]+", name)[:12]
        for count in range(len(words), 1, -1):
            prefix = " ".join(words[:count])
            meaningful = [w for w in words[:count] if w not in ENGLISH_STOP_WORDS]
            if count < min(3, len(words)) or len(meaningful) < 2 or len(prefix) < 7:
                continue
            if f" {prefix} " in f" {normalized} ":
                matched.append(title)
                topic = topic.replace(f" {prefix} ", " ")
                break
    noise = {"according", "book", "books", "example", "explain", "defined", "describe", "mean"}
    terms = [w for w in topic.split() if w not in ENGLISH_STOP_WORDS | noise]
    return matched, " OR ".join(dict.fromkeys(terms[:32]))


def focused_concept_order(rows, topic: str):
    """Prefer rare concept coverage/co-occurrence over repeated generic words.

    Rarity is estimated only within this bounded eligible source pool; it is not
    a relevance probability or a corpus-wide inverse-document-frequency score.
    """
    terms = [t.lower() for t in topic.split(" OR ")]
    texts = [" " + " ".join(re.findall(r"[^\W_]+", row[0].text.lower())) + " " for row in rows]
    frequencies = {term: sum(f" {term} " in text for text in texts) for term in terms}
    weights = {term: 1 + log((len(rows) + 1) / (frequencies[term] + 1)) for term in terms}
    scored = []
    for row, text in zip(rows, texts, strict=True):
        coverage = sum(weights[term] for term in terms if f" {term} " in text)
        phrases = sum(
            2 * (weights[left] + weights[right])
            for left, right in zip(terms, terms[1:])
            if f" {left} {right} " in text
        )
        scored.append((coverage + phrases, row))
    return [
        row for _, row in sorted(scored, key=lambda x: (-x[0], -float(x[1][3]), str(x[1][0].id)))
    ]


def source_role_intents(query: str, topic: str):
    """English question cues, not book-specific rules or quality labels."""
    noise = {"claim", "claims", "explain", "explanation", "according", "apparently", "might"}
    terms = [term for term in topic.split(" OR ") if term not in noise]
    core = " ".join(dict.fromkeys(terms[:2]))
    roles = []
    if re.search(r"\b(what|define|defined|definition|mean|means|differ)\b", query, re.I):
        roles.append(("definition", r"\m(means|defined|definition|refers|places|called)\M"))
    if re.search(
        r"\b(does|always|every|never|prove|proves|limit|limits|guarantee|worse|risk)\b", query, re.I
    ):
        roles.append(
            ("qualification", r"\m(cannot|impossible|not|never|unless|limits|risk|wrong|however)\M")
        )
    if re.search(r"\b(worse|backfire|opposite|wrong direction)\b", query, re.I):
        roles = [(role, pattern) for role, pattern in roles if role != "qualification"]
        roles.append(("direction", r"\m(wrong|opposite|reverse|backfire)\M"))
    return core, roles


def source_role_order(rows, role: str, core: str):
    """Prefer explicit nearby definitions/caveats, never infer their truth."""
    patterns = (
        [
            (r"\b(?:is|are|means|points)[\s—:,-]+(?:a |the )?places?\b", 5),
            (r"\b(?:defined as|refers to|definition|means that)\b", 1),
        ]
        if role == "definition"
        else [
            (r"\b(?:impossible to|do not claim|don['’]t claim)\b", 8),
            (r"\b(?:not necessarily|not a recipe|wrong direction)\b", 4),
            (r"\b(?:cannot|can['’]t|not|never|however|limits|risk|unless)\b", 1),
        ]
    )
    if role == "direction":
        patterns = [(r"\b(?:wrong direction|opposite|backfire|reverse)\b", 8)]
    terms = core.split()

    def score(row):
        text = re.sub(r"\s+", " ", row[0].text.lower())
        positions = [
            m.start() for t in terms for m in re.finditer(r"\b" + re.escape(t) + r"\w*\b", text)
        ]
        proximity = sum(
            max(
                (
                    weight / (1 + min((abs(m.start() - p) for p in positions), default=10000) / 200)
                    for m in re.finditer(pattern, text)
                ),
                default=0,
            )
            for pattern, weight in patterns
        )
        return (-proximity, -float(row[3]), str(row[0].id))

    return sorted(rows, key=score)


def ranked_query(db, statement, timeout_ms):
    """A failed optional search rolls back SQL state, not successful evidence."""
    try:
        with db.begin_nested():
            previous = db.scalar(select(func.current_setting("statement_timeout")))
            db.execute(select(func.set_config("statement_timeout", f"{timeout_ms}ms", True)))
            rows = db.execute(statement).all()
            db.execute(select(func.set_config("statement_timeout", previous, True)))
            return rows
    except SQLAlchemyError:
        return None


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
    # Bounded API concurrency must not multiply parallel hash-query shared
    # memory across the large local corpus (Docker's default /dev/shm is 64MB).
    db.execute(sql_text("SET LOCAL max_parallel_workers_per_gather=0"))
    conditions = [
        Collection.slug.in_(request.collection_ids),
        *current_source_conditions(settings, subject),
    ]
    filters = request.filters
    if settings.quality_excluded_chunk_ids:
        conditions.append(Chunk.id.not_in(settings.quality_excluded_chunk_ids))
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
    keyword_ok = False
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
        rows = ranked_query(
            db,
            base.with_only_columns(Chunk.id, score.label("score"))
            .where(Chunk.search_vector.op("@@")(query))
            .order_by(score.desc(), Chunk.id)
            .limit(limit),
            min(settings.database_statement_timeout_ms, 4000),
        )
        keyword_ok = rows is not None
        if not rows:
            for alternative in lexical_alternatives(request.query, ENGLISH_STOP_WORDS):
                broad_keyword = True
                broad_query = func.websearch_to_tsquery("english", alternative)
                broad_score = func.ts_rank_cd(Chunk.search_vector, broad_query)
                candidate_rows = ranked_query(
                    db,
                    base.with_only_columns(Chunk.id, broad_score.label("score"))
                    .where(Chunk.search_vector.op("@@")(broad_query))
                    .order_by(broad_score.desc(), Chunk.id)
                    .limit(limit),
                    min(settings.database_statement_timeout_ms, 4000),
                )
                keyword_ok = keyword_ok or candidate_rows is not None
                if candidate_rows:
                    rows = candidate_rows
                    break
        db.execute(select(func.set_config("enable_nestloop", previous_nestloop, True)))
        if not keyword_ok and mode == "keyword":
            raise EmbeddingError("KEYWORD_RETRIEVAL_UNAVAILABLE")
        add_pool(hydrate(rows or []))
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
            if not keyword_ok:
                raise EmbeddingError("RETRIEVAL_UNAVAILABLE") from None
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
            ranks = ranked_query(
                db,
                base.join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
                .with_only_columns(Chunk.id, (1 - distance).label("score"))
                .where(
                    column.is_not(None),
                    ChunkEmbedding.identity == identity,
                    ChunkEmbedding.dimensions == embedder.dimensions,
                )
                .order_by(distance, Chunk.id)
                .limit(limit),
                min(settings.database_statement_timeout_ms, 8000),
            )
            vector_ok = ranks is not None
            ranks = ranks or []
            if embedder.dimensions == 1536 and embedder.legacy_identity:
                legacy_distance = Chunk.embedding.cosine_distance(vector)
                # Legacy raw OpenAI vectors are usable only for their exact original
                # endpoint/model, and only when a new matching row is absent.
                exists = (
                    select(ChunkEmbedding.chunk_id)
                    .where(ChunkEmbedding.chunk_id == Chunk.id, ChunkEmbedding.identity == identity)
                    .exists()
                )
                legacy_ranks = ranked_query(
                    db,
                    base.with_only_columns(Chunk.id, (1 - legacy_distance).label("score"))
                    .where(
                        Chunk.embedding.is_not(None),
                        Chunk.embedding_identity == embedder.legacy_identity,
                        ~exists,
                    )
                    .order_by(legacy_distance, Chunk.id)
                    .limit(limit),
                    min(settings.database_statement_timeout_ms, 8000),
                )
                vector_ok = vector_ok or legacy_ranks is not None
                ranks += legacy_ranks or []
                ranks = sorted(ranks, key=lambda row: (-float(row[1]), str(row[0])))[:limit]
            # On a SQL error the transaction is aborted; rollback also resets
            # SET LOCAL. Do not mask that error by trying another SQL statement.
            db.execute(select(func.set_config("enable_nestloop", previous_nestloop, True)))
            if not vector_ok:
                if mode != "hybrid" or not keyword_ok:
                    raise EmbeddingError("VECTOR_RETRIEVAL_UNAVAILABLE")
                mode = "keyword"
                fallback_reason = "VECTOR_RETRIEVAL_UNAVAILABLE"
            elif mode == "hybrid" and not keyword_ok:
                mode = "semantic"
                fallback_reason = "KEYWORD_RETRIEVAL_UNAVAILABLE"
            if vector_ok:
                add_pool(hydrate(ranks))
            if mode == "semantic" and not keyword_ok and len(pools) > 1:
                pools = pools[1:]
    # A named-source question needs concept-bearing pages from that source,
    # rather than introductory pages matching the title itself. All rows still
    # pass the original source/reader/revision/filter predicate via `base`.
    focused = False
    focused_lead: list[str] = []
    titles, topic = named_source_topic(request.query, [row[1].title for row in rows_by_id.values()])
    if titles and topic:
        sources = [row[1] for row in rows_by_id.values() if row[1].title in titles]
        source_ids = {doc.id for doc in sources if not doc.book_id}
        book_ids = {doc.book_id for doc in sources if doc.book_id}
        focus_query = func.websearch_to_tsquery("english", topic)
        focus_score = func.ts_rank_cd(Chunk.search_vector, focus_query, 32)
        focus_base = (
            base.with_only_columns(Chunk.id, focus_score.label("score"))
            .where(or_(Document.id.in_(source_ids), Document.book_id.in_(book_ids)))
            .order_by(focus_score.desc(), Chunk.id)
            .limit(limit)
        )
        # Try all concept terms first. Otherwise repeated generic words can
        # crowd a rare definition out of even the bounded source-only pool.
        strict_focus = func.plainto_tsquery("english", topic.replace(" OR ", " "))
        focus_rows = db.execute(focus_base.where(Chunk.search_vector.op("@@")(strict_focus))).all()
        if not focus_rows:
            focus_rows = db.execute(
                focus_base.where(Chunk.search_vector.op("@@")(focus_query))
            ).all()
        concept_rows = focused_concept_order(hydrate(focus_rows), topic) if focus_rows else []
        core, roles = source_role_intents(request.query, topic)
        role_leads = []
        if core:
            core_query = func.plainto_tsquery("english", core)
            for role, pattern in roles:
                role_rows = hydrate(
                    db.execute(
                        focus_base.where(
                            Chunk.search_vector.op("@@")(core_query), Chunk.text.op("~*")(pattern)
                        )
                    ).all()
                )
                ordered = source_role_order(role_rows, role, core)
                # One candidate per eligible named source for each requested role.
                seen_sources: Counter = Counter()
                for row in ordered:
                    key = row[1].book_id or row[1].id
                    if seen_sources[key] < (2 if role == "direction" else 1):
                        role_leads.append(row)
                        seen_sources[key] += 1
                concept_rows.extend(ordered)
        if concept_rows:
            add_pool(concept_rows)
            lead_counts: Counter = Counter()
            for row in role_leads + concept_rows:
                key = row[1].book_id or row[1].id
                canonical = canonical_text[row[0].text]
                if lead_counts[key] >= 3 or canonical in focused_lead:
                    continue
                lead_counts[key] += 1
                focused_lead.append(canonical)
                if len(focused_lead) >= min(6, request.top_k):
                    break
            focused = True

    bonus_by_id: dict[str, float] = {}
    query_terms = {w.lower() for w in re.findall(r"[^\W_]{3,}", request.query, flags=re.UNICODE)}
    if query_terms and mode == "hybrid":
        for key, (chunk, doc, _, _) in rows_by_id.items():
            title_words = set(
                re.findall(r"[^\W_]{3,}", (doc.title or "").lower(), flags=re.UNICODE)
            )
            heading_words = set(
                re.findall(r"[^\W_]{3,}", (chunk.heading_path or "").lower(), flags=re.UNICODE)
            )
            title_overlap = len(query_terms & title_words)
            heading_overlap = len(query_terms & heading_words)
            if title_overlap or heading_overlap:
                bonus_by_id[key] = min(0.008, title_overlap * 0.003 + heading_overlap * 0.002)

    # An OR-broadened query has weaker lexical agreement than the original FTS
    # query. Keep those candidates but reduce their influence in hybrid fusion.
    weights = [0.5 if broad_keyword else 1.0, 1.0] if mode == "hybrid" else [1.0]
    if focused:
        weights.append(3.0)
    ranked = (
        rrf(pools, weights=weights, bonus_by_id=bonus_by_id)
        if mode == "hybrid" or focused
        else [(key, scores_by_id[key]) for key in pools[0]]
    )
    if focused_lead:
        # Explicit source requests receive a small concept-bearing lead from
        # each named book. Title-heavy intro pages cannot outvote that lead by
        # agreeing across two otherwise broad retrieval channels.
        lead_order = {key: i for i, key in enumerate(dict.fromkeys(focused_lead))}
        ranked.sort(key=lambda pair: (0, lead_order[pair[0]]) if pair[0] in lead_order else (1, 0))
    results: list[Evidence] = []
    counts: Counter = Counter()
    graph_paths = {}
    if settings.graph_enabled and request.graph_expand and not focused and request.top_k >= 3:
        from app.graph.service import neighbors

        # Preserve the leading search evidence. Bounded graph neighbors add
        # cross-source candidates, never authority or inferred author agreement.
        try:
            # An optional derived index must not invalidate ordinary retrieval
            # when a graph query times out or fails. Roll back its SQL state.
            with db.begin_nested():
                expanded = neighbors(
                    db,
                    base,
                    [rows_by_id[k][0].id for k, _ in ranked[: min(3, request.top_k)]],
                    request.query,
                    limit=2 if request.top_k >= 8 else 1,
                    excluded_texts=[rows_by_id[k][0].text for k, _ in ranked[: request.top_k]],
                )
        except SQLAlchemyError:
            expanded = []
            fallback_reason = "GRAPH_EXPANSION_UNAVAILABLE"
        graph_rank = []
        for chunk, doc, slug, graph_score, path in expanded:
            key = str(chunk.id)
            rows_by_id[key] = (chunk, doc, slug, graph_score)
            graph_paths[key] = path
            graph_rank.append((key, graph_score))
        if graph_rank:
            keep = max(2, request.top_k - len(graph_rank))
            ranked = ranked[:keep] + graph_rank + ranked[keep:]
    emitted = set()
    for key, score_value in ranked:
        if key in emitted:
            continue
        emitted.add(key)
        chunk, doc, slug, _ = rows_by_id[key]
        if chunk.id in settings.quality_excluded_chunk_ids:
            continue
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
            or (
                book_record.visibility == "PRIVATE"
                and not can_read_private_book(book_record, slug, subject, settings)
            )
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
                discovery_path=graph_paths.get(key, []),
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
                full_text_length=len(chunk.text),
                is_truncated=len(chunk.text) > len(chunk.text[:240]),
                rank=len(results) + 1,
                score=score_value,
            )
        )
        if len(results) == request.top_k:
            break
    return RetrievalResponse(
        retrieval_mode_used=mode,
        fallback_reason=fallback_reason,
        score_semantics=(
            "Named-source definition/qualification/direction and concept lead (up to three passages per source), then weighted RRF with concept pool weight=3; bounded-pool lexical role cues, rarity and phrase coverage; not a probability"
            if focused
            else {
                "keyword": "PostgreSQL ts_rank_cd; not a probability",
                "semantic": "cosine similarity; not a probability",
                "hybrid": "RRF sum(weight/(60+rank)); broadened keyword weight=0.5, otherwise weights=1; plus title/heading overlap bonus capped at 0.008; not a probability",
            }[mode]
        )
        + (
            "; bounded graph neighbors use lexical topic hints; their scores are not comparable to RRF or cosine scores"
            if graph_paths
            else ""
        ),
        results=results,
    )
