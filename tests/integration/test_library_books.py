import uuid

import pymupdf
import pytest
from sqlalchemy import select

from app.api.schemas import Filters, RetrievalRequest
from app.config import Settings
from app.db.models import Chunk, Collection, Document, LibraryBook
from app.library.books import _prepare_pages, ingest_parts
from app.library.catalog import digest
from app.retrieval.hybrid import retrieve

pytestmark = pytest.mark.integration


def test_catalog_sync_requires_active_chunks_and_tracks_revocation(db, tmp_path):
    from app.library.catalog import atomic_json, read_catalog
    from app.library.status import sync_status

    col = db.scalar(select(Collection).where(Collection.slug == "personal-library"))
    if not col:
        col = Collection(slug="personal-library", title="Private", visibility="PRIVATE")
        db.add(col)
        db.commit()
    row = resource(tmp_path, pages=2)
    row.update(collection="personal-library", root=str(tmp_path))
    output = tmp_path / "catalog"
    output.mkdir()
    atomic_json(output / "library.json", {"schema_version": 1, "resources": [row]})
    book = LibraryBook(
        id=uuid.UUID(row["id"]),
        collection_id=col.id,
        title=row["title"],
        approved=True,
        visibility="PRIVATE",
        owner_id=uuid.UUID(row["access"]["owner_id"]),
        active_generation=0,
        status="INDEXED",
    )
    db.add(book)
    db.commit()
    assert sync_status(db, output)["retrievable_references"] == 0
    assert (
        read_catalog(output / "library.json")["resources"][0]["ingestion"]["status"]
        == "INDEX_FAILED"
    )
    state = _prepare_pages(row, tmp_path / "prepared", 10)
    ingest_parts(db, row, state, "personal-library", Settings(), limit=100)
    assert sync_status(db, output)["retrievable_references"] == 1
    book.approved = False
    book.status = "REVOKED"
    db.commit()
    assert sync_status(db, output)["retrievable_references"] == 0
    assert read_catalog(output / "library.json")["resources"][0]["ingestion"]["status"] == "REVOKED"


def resource(tmp_path, pages=20):
    path = tmp_path / "book.pdf"
    with pymupdf.open() as pdf:
        for i in range(pages):
            page = pdf.new_page()
            page.insert_textbox(
                (40, 40, 550, 800),
                (f"Original systems feedback café research page {i + 1}. " * 60),
                fontsize=8,
            )
        pdf.set_toc([[1, "Verified outline chapter", 1]])
        pdf.save(path)
    sha = digest(path)
    return {
        "id": str(uuid.uuid4()),
        "absolute_path": str(path),
        "sha256": sha,
        "title": "Original book fixture",
        "authors": ["Fixture author"],
        "edition": None,
        "format": "pdf",
        "presence": "PRESENT",
        "category": "strategy-and-decision",
        "access": {"visibility": "PRIVATE", "owner_id": str(uuid.uuid4())},
        "rights": {
            "permission_status": "APPROVED",
            "approved_sha256": sha,
            "permitted_uses": ["local_index", "private_retrieval"],
            "evidence": "Original test material",
        },
    }


def test_resumable_book_atomic_activation_owner_filters_and_revocation(db, tmp_path):
    col = db.scalar(select(Collection).where(Collection.slug == "personal-library"))
    if not col:
        col = Collection(slug="personal-library", title="Private", visibility="PRIVATE")
        db.add(col)
        db.commit()
    row = resource(tmp_path, pages=140)
    state = _prepare_pages(row, tmp_path / "prepared", 10)
    assert not state["complete"] and state["next_page"] == 11
    while not state["complete"]:
        state = _prepare_pages(row, tmp_path / "prepared", 40)
    assert state["complete"] and state["total_pdf_pages"] == 140
    assert all(p["last_page"] - p["first_page"] < 8 for p in state["parts"])
    assert (
        ingest_parts(db, row, state, "personal-library", Settings(), limit=1)["status"]
        == "PROCESSING"
    )
    request = RetrievalRequest(
        query="systems feedback", collection_ids=["personal-library"], mode="keyword"
    )
    owner = row["access"]["owner_id"]
    assert not retrieve(db, request, Settings(), subject=owner).results
    result = ingest_parts(db, row, state, "personal-library", Settings(), limit=100)
    assert result["status"] == "INDEXED"
    ids = set(db.scalars(select(Chunk.id)))
    assert len(ids) > 256
    assert (
        ingest_parts(db, row, state, "personal-library", Settings(), limit=20)["status"]
        == "INDEXED"
    )
    assert set(db.scalars(select(Chunk.id))) == ids
    hits = retrieve(db, request, Settings(), subject=owner).results
    assert hits and hits[0].book_id == uuid.UUID(row["id"])
    assert hits[0].author == "Fixture author" and hits[0].page_start >= 1
    assert hits[0].chapter == "Verified outline chapter"
    assert hits[0].source_url is None and str(tmp_path) not in hits[0].model_dump_json()
    assert not retrieve(db, request, Settings(), subject=str(uuid.uuid4())).results
    with pytest.raises(PermissionError):
        retrieve(db, request, Settings())
    assert not retrieve(
        db, RetrievalRequest(query="systems feedback", mode="keyword"), Settings()
    ).results
    filtered = request.model_copy(update={"filters": Filters(author=["wrong author"])})
    assert not retrieve(db, filtered, Settings(), subject=owner).results
    # Change only the final page. Prior evidence remains visible during staging;
    # unchanged parts retain the same document/chunk IDs at atomic activation.
    with pymupdf.open(row["absolute_path"]) as pdf:
        pdf[-1].insert_text((50, 790), "New final-page observation")
        pdf.saveIncr()
    row["sha256"] = digest(__import__("pathlib").Path(row["absolute_path"]))
    row["rights"]["approved_sha256"] = row["sha256"]
    updated = _prepare_pages(row, tmp_path / "updated", 100)
    updated = _prepare_pages(row, tmp_path / "updated", 100)
    outcome = ingest_parts(db, row, updated, "personal-library", Settings(), limit=100)
    assert outcome["status"] == "INDEXED" and outcome["reused_unchanged_parts"] > 10
    active_ids = set(
        db.scalars(
            select(Chunk.id)
            .join(Document)
            .where(Document.book_generation == 2, Chunk.revision == Document.active_revision)
        )
    )
    assert len(active_ids & ids) > len(ids) * 0.9
    book = db.get(LibraryBook, uuid.UUID(row["id"]))
    book.approved = False
    db.commit()
    assert not retrieve(db, request, Settings(), subject=owner).results
    assert ids <= set(db.scalars(select(Chunk.id)))


def test_incomplete_ocr_or_unapproved_book_cannot_activate(db, tmp_path):
    row = resource(tmp_path, pages=2)
    state = _prepare_pages(row, tmp_path / "prepared", 1)
    with pytest.raises(ValueError, match="BOOK_PREPARATION_INCOMPLETE"):
        ingest_parts(db, row, state, "personal-library", Settings())
    state = _prepare_pages(row, tmp_path / "prepared", 10)
    state["ocr_required_pages"] = [1]
    with pytest.raises(ValueError, match="BOOK_OCR_REVIEW_REQUIRED"):
        ingest_parts(db, row, state, "personal-library", Settings())
    row["rights"]["permitted_uses"] = []
    with pytest.raises(ValueError, match="SOURCE_PERMISSION_REQUIRED"):
        ingest_parts(db, row, state, "personal-library", Settings())
    assert not list(db.scalars(select(Document)))


def test_explicit_partial_coverage_is_cited_and_never_claims_image_page_text(db, tmp_path):
    from pathlib import Path

    row = resource(tmp_path, pages=1)
    path = tmp_path / "partial.pdf"
    with pymupdf.open(row["absolute_path"]) as pdf:
        page = pdf.new_page()
        page.draw_rect((50, 50, 150, 150), fill=(0, 0, 0))
        pdf.save(path)
    row["absolute_path"] = str(path)
    row["sha256"] = digest(Path(path))
    row["rights"]["approved_sha256"] = row["sha256"]
    state = _prepare_pages(row, tmp_path / "parts", 10)
    assert state["ocr_required_pages"] == [2]
    outcome = ingest_parts(db, row, state, "personal-library", Settings(), allow_partial=True)
    assert outcome["status"] == "PARTIALLY_INDEXED"
    hits = retrieve(
        db,
        RetrievalRequest(
            query="systems feedback", collection_ids=["personal-library"], mode="keyword"
        ),
        Settings(),
        subject=row["access"]["owner_id"],
    ).results
    assert hits and all(hit.page_start == 1 and hit.coverage_note for hit in hits)


def test_revocation_before_registration_blocks_a_stale_approved_worker_snapshot(db, tmp_path):
    from app.library.books import revoke_book

    row = resource(tmp_path, pages=2)
    row["collection"] = "personal-library"
    state = _prepare_pages(row, tmp_path / "parts", 10)
    revoke_book(db, row, Settings())
    with pytest.raises(ValueError, match="BOOK_REVOKED_OR_SCOPE_CHANGED"):
        ingest_parts(db, row, state, "personal-library", Settings())
    assert not list(db.scalars(select(Chunk)))
