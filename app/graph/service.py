import hashlib
import re
from typing import Any
from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    Chunk,
    Collection,
    Document,
    GraphPassageTopic as Link,
    GraphState,
    GraphTopic,
    LibraryBook,
)
from app.graph.topics import BY_ID, RELATED, TOPICS, VERSION, PATTERNS, mentions
from app.library.eligibility import current_source_conditions


def source_id():
    return func.coalesce(Document.book_id, Document.id)


def source_title():
    return func.coalesce(LibraryBook.title, Document.title)


def scoped_base(settings, subject, collections):
    allowed = set(settings.allowed_collections) | set(settings.private_collections)
    if not set(collections) <= allowed:
        raise PermissionError("COLLECTION_NOT_ALLOWED")
    if set(collections) & set(settings.private_collections) and not subject:
        raise PermissionError("PRIVATE_SCOPE_REQUIRED")
    return (
        select(Chunk, Document, Collection.slug)
        .join(Document, Document.id == Chunk.document_id)
        .join(Collection, Collection.id == Document.collection_id)
        .outerjoin(LibraryBook, LibraryBook.id == Document.book_id)
        .where(Collection.slug.in_(collections), *current_source_conditions(settings, subject))
    )


def link_conditions():
    return [
        Link.extractor_version == VERSION,
        func.substr(Chunk.text, Link.anchor_start + 1, Link.anchor_end - Link.anchor_start)
        == Link.anchor,
    ]


def valid_link(chunk, link):
    return (
        link.extractor_version == VERSION
        and hashlib.sha256(chunk.text.encode()).hexdigest() == link.text_sha256
        and chunk.text[link.anchor_start : link.anchor_end] == link.anchor
        and link.topic_id in BY_ID
    )


def seed_topics(db):
    for slug, label, domain, _ in TOPICS:
        stmt = insert(GraphTopic).values(id=slug, label=label, domain=domain)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[GraphTopic.id], set_={"label": label, "domain": domain}
            )
        )


def index_chunks(db, chunks):
    rows, mapped = [], 0
    for chunk in chunks:
        found = mentions(chunk.text)
        mapped += bool(found)
        digest = hashlib.sha256(chunk.text.encode()).hexdigest()
        for topic, start, end, anchor in found:
            rows.append(
                dict(
                    chunk_id=chunk.id,
                    topic_id=topic,
                    extractor_version=VERSION,
                    text_sha256=digest,
                    anchor_start=start,
                    anchor_end=end,
                    anchor=anchor,
                )
            )
    for offset in range(0, len(rows), 500):
        stmt = insert(Link).values(rows[offset : offset + 500])
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Link.chunk_id, Link.topic_id],
                set_={
                    k: getattr(stmt.excluded, k)
                    for k in [
                        "extractor_version",
                        "text_sha256",
                        "anchor_start",
                        "anchor_end",
                        "anchor",
                    ]
                },
            )
        )
    return mapped, len(rows)


def rebuild(db, progress=None):
    """One atomic derived-index transaction; never edits source or vector rows."""
    db.execute(text("SET LOCAL statement_timeout=30000"))
    db.execute(text("SET LOCAL enable_nestloop=off"))
    seed_topics(db)
    # All currently approved sources; reader grants are applied at every query.
    statement = (
        select(Chunk.id, Chunk.text)
        .join(Document, Chunk.document_id == Document.id)
        .outerjoin(LibraryBook, Document.book_id == LibraryBook.id)
        .where(
            Document.approved.is_(True),
            Document.status != "DELETED",
            Chunk.revision == Document.active_revision,
            or_(
                Document.book_id.is_(None),
                (
                    LibraryBook.approved.is_(True)
                    & LibraryBook.status.in_(["INDEXED", "PARTIALLY_INDEXED"])
                    & (Document.book_generation == LibraryBook.active_generation)
                ),
            ),
        )
        .execution_options(yield_per=500)
    )
    scanned = mapped = links = 0
    batch = []
    for chunk in db.execute(statement):
        batch.append(chunk)
        if len(batch) == 500:
            m, count = index_chunks(db, batch)
            scanned += len(batch)
            mapped += m
            links += count
            batch = []
            if progress and scanned % 10000 == 0:
                progress({"scanned_chunks": scanned, "mapped_chunks": mapped, "links": links})
    if batch:
        m, count = index_chunks(db, batch)
        scanned += len(batch)
        mapped += m
        links += count
    values = dict(
        id=1,
        extractor_version=VERSION,
        built_at=datetime.now(UTC),
        scanned_chunks=scanned,
        mapped_chunks=mapped,
        links=links,
    )
    stmt = insert(GraphState).values(**values)
    db.execute(stmt.on_conflict_do_update(index_elements=[GraphState.id], set_=values))
    db.commit()
    return {
        "scanned_chunks": scanned,
        "mapped_chunks": mapped,
        "links": links,
        "topics": len(TOPICS),
        "version": VERSION,
    }


def ready(db):
    state = db.get(GraphState, 1)
    return state if state and state.extractor_version == VERSION else None


def index_like(content):
    """Conservative navigation-page rejection for expansion, not source deletion."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if re.match(r"\s*(index|table of contents|bibliography|references)\s*(\n|$)", content, re.I):
        return True
    page_rows = sum(
        bool(re.search(r"(?:,\s*|^|\s)\d{1,4}(?:[–−-]\d{1,4})?[ft]?$", line)) for line in lines
    )
    return (
        len(lines) >= 12
        and page_rows >= 5
        and sum(len(line) < 65 for line in lines) / len(lines) > 0.8
    )


def neighbors(db, base, seed_ids, query, limit=2, *, excluded_texts=()):
    """One related-topic hop. All seeds and targets inherit the same filters."""
    if not seed_ids or not ready(db):
        return []
    db.execute(text("SET LOCAL enable_nestloop=off"))
    db.execute(text("SET LOCAL max_parallel_workers_per_gather=0"))
    seed_rows = db.execute(
        base.add_columns(Link)
        .join(Link, Link.chunk_id == Chunk.id)
        .where(Chunk.id.in_(seed_ids), *link_conditions())
    ).all()
    seeds: dict[str, str] = {}
    seed_books = set()
    for chunk, doc, _, link in seed_rows:
        if valid_link(chunk, link):
            seeds.setdefault(link.topic_id, str(chunk.id))
            seed_books.add(doc.book_id or doc.id)
    direct = [topic for topic in seeds if PATTERNS[topic].search(query)]
    topics = (direct or list(seeds))[:4]
    paths = {t: (t, seeds[t], "shared_topic") for t in topics}
    for a, b in RELATED:
        if len(paths) >= 8:
            break
        if a in topics and b not in paths:
            paths[b] = (a, seeds[a], "related_topic")
        elif b in topics and a not in paths:
            paths[a] = (b, seeds[b], "related_topic")
    if not paths:
        return []
    requested_topics = {topic for topic, pattern in PATTERNS.items() if pattern.search(query)}
    # When a question explicitly names multiple mapped topics, follow those
    # connections before introducing an adjacent but unrequested discipline.
    if len(requested_topics) >= 2 and requested_topics.intersection(paths):
        paths = {topic: path for topic, path in paths.items() if topic in requested_topics}
    # Lexical score is a ranking hint, not entailment or a learned reranker.
    terms = [
        w
        for w in re.findall(r"[^\W_]{3,}", query)
        if w.lower()
        not in {"the", "and", "what", "how", "should", "with", "from", "that", "this", "our"}
    ][:24]
    lexical = func.ts_rank_cd(
        Chunk.search_vector, func.websearch_to_tsquery("english", " OR ".join(terms) or query)
    )
    ids = db.execute(
        base.join(Link, Link.chunk_id == Chunk.id)
        .where(Link.topic_id.in_(paths), ~source_id().in_(seed_books), *link_conditions())
        .with_only_columns(
            Chunk.id, func.max(lexical).label("lexical"), func.count().label("overlap")
        )
        .group_by(Chunk.id)
        .order_by(
            func.max(case((Link.topic_id.in_(requested_topics), 1), else_=0)).desc(),
            func.max(lexical).desc(),
            func.count().desc(),
            Chunk.id,
        )
        .limit(60)
    ).all()
    found, books = [], set()
    fingerprints = {
        hashlib.sha256(" ".join(content.casefold().split()).encode()).hexdigest()
        for content in excluded_texts
    }
    candidates = (
        db.execute(
            base.add_columns(Link)
            .join(Link, Link.chunk_id == Chunk.id)
            .where(Chunk.id.in_([r[0] for r in ids]), Link.topic_id.in_(paths), *link_conditions())
        ).all()
        if ids
        else []
    )
    by_id: dict[Any, list[Any]] = {}
    for row in candidates:
        by_id.setdefault(row[0].id, []).append(row)
    for chunk_id, score, _ in ids:
        rows = by_id.get(chunk_id, [])
        for chunk, doc, slug, link in rows:
            key = doc.book_id or doc.id
            fingerprint = hashlib.sha256(
                " ".join(chunk.text.casefold().split()).encode()
            ).hexdigest()
            if (
                key in books
                or fingerprint in fingerprints
                or index_like(chunk.text)
                or not valid_link(chunk, link)
            ):
                continue
            via, seed, relation = paths[link.topic_id]
            path = [f"Seed passage {seed}", BY_ID[via][1], relation, BY_ID[link.topic_id][1]]
            found.append((chunk, doc, slug, float(score), path))
            books.add(key)
            fingerprints.add(fingerprint)
            break
        if len(found) >= limit:
            break
    return found


def browse(db, settings, subject, body):
    db.execute(text("SET LOCAL enable_nestloop=off"))
    db.execute(text("SET LOCAL max_parallel_workers_per_gather=0"))
    base = scoped_base(settings, subject, body.collection_ids)
    state = ready(db)
    if not settings.graph_enabled or not state:
        return {
            "ready": False,
            "method": VERSION,
            "topics": [],
            "sources": [],
            "edges": [],
            "related_topics": [],
            "summary": {},
        }
    if body.topic_id and body.topic_id not in BY_ID:
        raise ValueError("TOPIC_NOT_FOUND")
    if body.query:
        related = [
            t[0]
            for t in TOPICS
            if body.query.casefold() in (t[1] + " " + " ".join(t[3])).casefold()
        ]
        base = base.where(
            or_(
                source_title().icontains(body.query, autoescape=True),
                Chunk.id.in_(
                    select(Link.chunk_id).where(
                        Link.topic_id.in_(related), Link.extractor_version == VERSION
                    )
                ),
            )
        )
    if body.source_id:
        base = base.where(source_id() == body.source_id)
    linked = base.join(Link, Link.chunk_id == Chunk.id).where(*link_conditions())
    source_base = base
    if body.topic_id:
        selected_ids = (
            linked.where(Link.topic_id == body.topic_id)
            .with_only_columns(source_id())
            .distinct()
            .correlate(None)
        )
        linked = linked.where(source_id().in_(selected_ids))
        source_base = base.where(source_id().in_(selected_ids))
    topic_counts = db.execute(
        linked.with_only_columns(
            Link.topic_id, func.count(func.distinct(source_id())), func.count()
        )
        .group_by(Link.topic_id)
        .order_by(func.count(func.distinct(source_id())).desc())
    ).all()
    sources = db.execute(
        source_base.with_only_columns(
            source_id().label("source"),
            source_title().label("title"),
            LibraryBook.author,
            func.count(func.distinct(Chunk.id)),
        )
        .group_by(source_id(), source_title(), LibraryBook.author)
        .order_by(source_title())
        .offset(body.offset)
        .limit(body.limit)
    ).all()
    matched_count = (
        db.scalar(source_base.with_only_columns(func.count(func.distinct(source_id())))) or 0
    )
    visible = [r[0] for r in sources]
    samples = {}
    if visible:
        for chunk, doc, _ in db.execute(
            source_base.where(source_id().in_(visible))
            .distinct(source_id())
            .order_by(source_id(), Chunk.id)
        ):
            samples[str(doc.book_id or doc.id)] = {
                "chunk_id": str(chunk.id),
                "document_id": str(doc.id),
                "revision": chunk.revision,
            }
    passage_rows = (
        db.execute(
            linked.add_columns(Link)
            .where(source_id().in_(visible))
            .distinct(source_id(), Link.topic_id)
            .order_by(source_id(), Link.topic_id, Chunk.id)
        ).all()
        if visible
        else []
    )
    edges = []
    for chunk, doc, slug, link in passage_rows:
        if not valid_link(chunk, link):
            continue
        edges.append(
            {
                "source_id": str(doc.book_id or doc.id),
                "topic_id": link.topic_id,
                "relation": "mentions",
                "method": VERSION,
                "chunk_id": str(chunk.id),
                "document_id": str(doc.id),
                "revision": chunk.revision,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "locator": chunk.heading_path,
                "anchor": link.anchor,
                "text_sha256": link.text_sha256,
                "collection_id": slug,
            }
        )
    eligible_count = db.scalar(base.with_only_columns(func.count(func.distinct(source_id())))) or 0
    mapped_count = (
        db.scalar(
            base.join(Link, Link.chunk_id == Chunk.id)
            .where(*link_conditions())
            .with_only_columns(func.count(func.distinct(source_id())))
        )
        or 0
    )
    ids = {t[0] for t in topic_counts}
    return {
        "ready": True,
        "method": VERSION,
        "built_at": state.built_at.isoformat(),
        "topics": [
            {"id": t, "label": BY_ID[t][1], "domain": BY_ID[t][2], "sources": n, "passages": p}
            for t, n, p in topic_counts
            if t in BY_ID
        ],
        "sources": [
            {
                "id": str(i),
                "title": title,
                "author": author,
                "passages": n,
                "sample": samples.get(str(i)),
            }
            for i, title, author, n in sources
        ],
        "edges": edges,
        "related_topics": [
            {"source": a, "target": b, "relation": "related_topic_hint"}
            for a, b in RELATED
            if a in ids and b in ids
        ],
        "summary": {
            "eligible_sources": eligible_count,
            "mapped_sources": mapped_count,
            "unmapped_sources": max(0, eligible_count - mapped_count),
            "displayed_sources": len(sources),
            "limited": body.offset + len(sources) < matched_count,
            "matched_sources": matched_count,
            "offset": body.offset,
        },
        "notice": "Starter topic mentions and curated topic relationships are discovery hints, not proof of support, agreement or full coverage. Inspect the original passages.",
    }
