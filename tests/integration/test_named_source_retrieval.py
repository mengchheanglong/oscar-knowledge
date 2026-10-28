import pytest
import uuid
from sqlalchemy import select

from app.api.schemas import Filters, RetrievalRequest
from app.config import Settings
from app.db.models import Chunk, Document, LibraryBook
from app.library.books import _prepare_pages, ingest_parts
from app.ingestion.pipeline import enqueue, process_job
from app.retrieval.hybrid import retrieve

pytestmark = pytest.mark.integration


def test_definition_and_caveat_survive_example_saturation_and_reader_exclusions(db, tmp_path):
    from tests.integration.test_library_books import resource

    row = resource(tmp_path, pages=1)
    row["title"] = "Aster Analytics: Measuring a Marketplace"
    prepared = _prepare_pages(row, tmp_path / "roles", 10)
    ingest_parts(db, row, prepared, "personal-library", Settings(), limit=100)
    book = db.get(LibraryBook, row["id"])
    doc = db.scalar(select(Document).where(Document.book_id == book.id))
    texts = [
        "Leverage points are places where a small change produces large effects.",
        "Leverage points cannot guarantee improvement. The direction can be wrong.",
    ]
    texts += [
        ("Leverage point improvement example always shows analytics. " * 20) + str(i)
        for i in range(110)
    ]
    ids = []
    for i, text in enumerate(texts):
        chunk = Chunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            collection_id=doc.collection_id,
            revision=doc.active_revision,
            ordinal=100 + i,
            text=text,
            char_count=len(text),
            token_estimate=100,
            page_start=10 + i,
            page_end=10 + i,
        )
        db.add(chunk)
        ids.append(chunk.id)
    db.commit()
    request = RetrievalRequest(
        query="What does Aster Analytics mean by a leverage point, and does it always guarantee improvement?",
        collection_ids=["personal-library"],
        top_k=2,
        mode="keyword",
    )
    owner = row["access"]["owner_id"]
    hits = retrieve(db, request, Settings(), subject=owner).results
    assert {hit.chunk_id for hit in hits} == set(ids[:2])
    assert not retrieve(db, request, Settings(), subject=str(uuid.uuid4())).results
    hits = retrieve(
        db, request, Settings(quality_excluded_chunk_ids=[ids[1]]), subject=owner
    ).results
    assert all(hit.chunk_id != ids[1] for hit in hits)


def test_focus_recovers_other_book_parts_without_broadening_reader_grants(db, tmp_path):
    from tests.integration.test_library_books import resource

    row = resource(tmp_path, pages=1)
    row["title"] = "Aster Analytics: Measuring a Marketplace"
    prepared = _prepare_pages(row, tmp_path / "prepared", 10)
    ingest_parts(db, row, prepared, "personal-library", Settings(), limit=100)
    book = db.get(LibraryBook, row["id"])
    first = db.scalar(select(Document).where(Document.book_id == book.id))
    definition_doc = Document(
        collection_id=first.collection_id,
        book_id=book.id,
        book_generation=book.active_generation,
        canonical_key="synthetic-next-part",
        local_path="synthetic-local-only",
        title=row["title"],
        content_type=".pdf",
        approved=True,
        active_revision=1,
        status="INDEXED",
    )
    db.add(definition_doc)
    db.flush()
    definition = (
        "Engaged buyers searched in the last thirty days. Buyers made at least one purchase."
    )
    target = Chunk(
        id=uuid.uuid4(),
        document_id=definition_doc.id,
        collection_id=first.collection_id,
        revision=1,
        ordinal=0,
        text=definition,
        char_count=len(definition),
        token_estimate=20,
        page_start=9,
        page_end=9,
    )
    db.add(target)
    for i in range(110):
        text = ("Aster Analytics buyers introductory material. " * 20) + str(i)
        db.add(
            Chunk(
                id=uuid.uuid4(),
                document_id=first.id,
                collection_id=first.collection_id,
                revision=first.active_revision,
                ordinal=100 + i,
                text=text,
                char_count=len(text),
                token_estimate=200,
                page_start=1,
                page_end=1,
            )
        )
    db.commit()
    request = RetrievalRequest(
        query="In Aster Analytics how are engaged buyers defined?",
        collection_ids=["personal-library"],
        top_k=1,
        mode="keyword",
    )
    owner = row["access"]["owner_id"]
    hits = retrieve(db, request, Settings(), subject=owner).results
    assert hits[0].chunk_id == target.id
    assert hits[0].document_id == definition_doc.id
    assert not retrieve(db, request, Settings(), subject=str(uuid.uuid4())).results
    denied = retrieve(db, request, Settings(quality_excluded_chunk_ids=[target.id]), subject=owner)
    assert all(hit.chunk_id != target.id for hit in denied.results)
    # A stale fragment of the same book is not eligible for focus expansion.
    definition_doc.book_generation = book.active_generation + 1
    db.commit()
    assert all(
        hit.chunk_id != target.id
        for hit in retrieve(db, request, Settings(), subject=owner).results
    )


def test_named_source_concept_pool_respects_exclusions_approval_and_filters(db, tmp_path):
    path = tmp_path / "original.md"
    path.write_text(
        "# Aster Analytics\n\n"
        + "Marketplace examples and analytics introductions. " * 80
        + "\n\n# Engaged buyers\n\nBuyers purchased at least once. Engaged buyers searched in the last thirty days. "
        * 30
    )
    job = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job.id, Settings()) == "INDEXED"
    doc = db.get(Document, job.document_id)
    doc.title = "Aster Analytics: Measuring a Marketplace"
    db.commit()
    request = RetrievalRequest(
        query="In Aster Analytics, how are buyers and engaged buyers defined?", mode="keyword"
    )
    result = retrieve(db, request, Settings())
    assert "Engaged buyers searched" in result.results[0].text
    rejected = result.results[0].chunk_id
    assert all(
        r.chunk_id != rejected
        for r in retrieve(db, request, Settings(quality_excluded_chunk_ids=[rejected])).results
    )
    request.filters = Filters(document_ids=[], title=["Another title"])
    assert not retrieve(db, request, Settings()).results
    request.filters = Filters()
    doc.approved = False
    db.commit()
    assert not retrieve(db, request, Settings()).results
