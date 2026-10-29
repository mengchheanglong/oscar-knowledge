import hashlib
import uuid

import pytest
from sqlalchemy import func, select, text as sql_text

from app.api.schemas import GraphBrowseRequest, RetrievalRequest
from app.config import Settings
from app.db.models import Chunk, Collection, Document, GraphPassageTopic, LibraryBook
from app.graph.service import browse, index_like, neighbors, rebuild, scoped_base
from app.graph.topics import mentions
from app.retrieval.hybrid import retrieve


def passage(db, title, content, *, owner=None):
    slug = "personal-library" if owner else "mba-business"
    collection = db.scalar(select(Collection).where(Collection.slug == slug))
    if not collection:
        collection = Collection(
            slug=slug, title=slug, visibility="PRIVATE" if owner else "CURATED_SHARED"
        )
        db.add(collection)
        db.flush()
    book = None
    if owner:
        book = LibraryBook(
            id=uuid.uuid4(),
            collection_id=collection.id,
            title=title,
            approved=True,
            visibility="PRIVATE",
            owner_id=owner,
            active_generation=1,
            status="INDEXED",
        )
        db.add(book)
        db.flush()
    doc = Document(
        collection_id=collection.id,
        canonical_key=str(uuid.uuid4()),
        local_path="synthetic.md",
        title=title,
        content_type=".md",
        approved=True,
        active_revision=1,
        status="INDEXED",
        book_id=book.id if book else None,
        book_generation=1 if book else None,
    )
    db.add(doc)
    db.flush()
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        collection_id=collection.id,
        revision=1,
        ordinal=0,
        text=content,
        char_count=len(content),
        token_estimate=len(content) // 4,
        page_start=7,
        page_end=7,
    )
    db.add(chunk)
    db.commit()
    return chunk, doc


def test_graph_is_derived_idempotent_and_source_anchored(db):
    text = "Customer discovery starts with listening to unmet needs. " * 8
    chunk, _ = passage(db, "Synthetic discovery", text)
    original = hashlib.sha256(chunk.text.encode()).hexdigest()
    first = rebuild(db)
    count = db.scalar(select(func.count()).select_from(GraphPassageTopic))
    second = rebuild(db)
    assert first == second
    assert count == db.scalar(select(func.count()).select_from(GraphPassageTopic))
    assert original == hashlib.sha256(db.get(Chunk, chunk.id).text.encode()).hexdigest()
    graph = browse(db, Settings(), None, GraphBrowseRequest())
    assert graph["ready"] and graph["edges"]
    for edge in graph["edges"]:
        assert edge["anchor"] in text and edge["text_sha256"] == original
        assert edge["page_start"] == 7 and edge["relation"] == "mentions"


def test_graph_rechecks_private_owner_exclusions_revision_and_mutated_anchors(db):
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    chunk, doc = passage(
        db,
        "Private synthetic",
        "A value proposition expresses customer benefit. " * 10,
        owner=owner,
    )
    rebuild(db)
    request = GraphBrowseRequest(collection_ids=["personal-library"])
    assert browse(db, Settings(), str(owner), request)["sources"]
    assert browse(db, Settings(), str(stranger), request)["sources"] == []
    denied = Settings(quality_excluded_chunk_ids=[chunk.id])
    assert browse(db, denied, str(owner), request)["sources"] == []
    with pytest.raises(PermissionError):
        browse(db, Settings(), None, request)
    chunk.text = "No matching topic exists in this changed synthetic source. " * 10
    db.commit()
    graph = browse(db, Settings(), str(owner), request)
    assert graph["edges"] == [] and graph["summary"]["unmapped_sources"] == 1
    doc.active_revision = 2
    db.commit()
    assert browse(db, Settings(), str(owner), request)["sources"] == []


def test_related_topic_expansion_finds_another_source_but_does_not_cross_scopes(db):
    seed, _ = passage(
        db, "Discovery seed", "Customer discovery identifies important unmet needs. " * 8
    )
    target, _ = passage(
        db,
        "Value target",
        "A value proposition explains how the offering relieves a customer problem. " * 8,
    )
    hidden, _ = passage(
        db,
        "Hidden private",
        "A value proposition explains a private customer benefit. " * 8,
        owner=uuid.uuid4(),
    )
    rebuild(db)
    settings = Settings()
    base = scoped_base(settings, None, ["mba-business"])
    result = neighbors(db, base, [seed.id], "customer discovery", 2)
    assert any(r[0].id == target.id for r in result)
    assert all(r[0].id != hidden.id for r in result)
    assert any("related_topic" in r[4] or "shared_topic" in r[4] for r in result)
    result = retrieve(
        db, RetrievalRequest(query="customer discovery", mode="keyword", top_k=3), settings
    )
    assert any(r.discovery_path for r in result.results)
    without = retrieve(
        db,
        RetrievalRequest(query="customer discovery", mode="keyword", top_k=3, graph_expand=False),
        settings,
    )
    assert all(not r.discovery_path for r in without.results)


def test_graph_can_follow_a_topic_across_books_and_browse_unmapped_sources(db):
    passage(db, "Alpha", "Customer discovery and pricing inform the value proposition. " * 10)
    passage(db, "Beta", "Pricing involves willingness to pay and contribution margin. " * 10)
    passage(db, "Unmapped", "A deliberately unmapped passage with no starter vocabulary. " * 10)
    rebuild(db)
    all_graph = browse(db, Settings(), None, GraphBrowseRequest())
    assert len(all_graph["sources"]) == 3 and all_graph["summary"]["unmapped_sources"] == 1
    assert all(s["sample"] for s in all_graph["sources"])
    pricing = browse(db, Settings(), None, GraphBrowseRequest(topic_id="pricing"))
    assert {s["title"] for s in pricing["sources"]} == {"Alpha", "Beta"}
    assert len(mentions("x" * 100 + " customer discovery")) >= 1


def test_expansion_avoids_indexes_duplicate_compilations_and_unrequested_topics(db):
    seed, _ = passage(db, "Discovery seed", "Customer discovery identifies unmet needs. " * 8)
    body = "A value proposition explains how customer benefit addresses a customer problem. " * 8
    passage(db, "Value original", body)
    passage(db, "Value duplicate", body)
    index = "Customer benefit, 28\nCustomer problem, 30\nValue proposition, 40\n" * 8
    passage(db, "Index without heading", index)
    passage(db, "Statistical detour", "Hypotheses and experiments use test statistics. " * 10)
    rebuild(db)
    result = neighbors(
        db,
        scoped_base(Settings(), None, ["mba-business"]),
        [seed.id],
        "customer discovery and value proposition",
        2,
    )
    assert len(result) == 1 and result[0][0].text == body
    assert index_like(index) and not index_like(body)
    assert (
        neighbors(
            db,
            scoped_base(Settings(), None, ["mba-business"]),
            [seed.id],
            "customer discovery and value proposition",
            2,
            excluded_texts=[body],
        )
        == []
    )


def test_failed_graph_sql_preserves_ordinary_retrieval(db, monkeypatch):
    seed, _ = passage(db, "Discovery seed", "Customer discovery identifies unmet needs. " * 8)
    rebuild(db)

    def broken_graph(*args, **kwargs):
        db.execute(sql_text("select 1 / 0"))

    monkeypatch.setattr("app.graph.service.neighbors", broken_graph)
    result = retrieve(
        db, RetrievalRequest(query="customer discovery", mode="keyword", top_k=3), Settings()
    )
    assert result.results[0].chunk_id == seed.id
    assert result.fallback_reason == "GRAPH_EXPANSION_UNAVAILABLE"
    assert db.scalar(sql_text("select 1")) == 1
