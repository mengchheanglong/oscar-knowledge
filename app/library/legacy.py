"""Verify legacy prepared references before binding their additive preparation identity."""

import json
import re
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db.models import Chunk, Collection, Document, LibraryBook
from app.ingestion.chunking import chunk_segments
from app.ingestion.loaders import load
from app.library.books import preparation_identity, require_shared_permission
from app.library.catalog import digest
from app.library.source import verify_source


def adopt_legacy_preparation(db, row, state, settings, *, apply=False):
    import pymupdf

    require_shared_permission(row)
    verify_source(row, force=True)
    book = db.get(LibraryBook, uuid.UUID(row["id"]))
    if (
        not book
        or not book.approved
        or book.preparation_sha256
        or not state["complete"]
        or book.source_sha256 != row["sha256"]
    ):
        raise ValueError("LEGACY_PREPARATION_NOT_ELIGIBLE")
    collection = db.get(Collection, book.collection_id)
    if (
        str(book.owner_id) != row["access"].get("owner_id")
        or book.visibility != row["access"]["visibility"]
        or not collection
        or collection.slug != row["collection"]
    ):
        raise ValueError("LEGACY_PREPARATION_SCOPE_MISMATCH")
    generation = book.active_generation
    documents = list(
        db.scalars(
            select(Document).where(
                Document.book_id == book.id, Document.book_generation == generation
            )
        )
    )
    by_path = {str(Path(d.local_path).resolve()): d for d in documents}
    if len(documents) != len(state["parts"]):
        raise ValueError("LEGACY_PREPARATION_PART_COUNT")
    with pymupdf.open(row["absolute_path"]) as pdf:
        for part in state["parts"]:
            path = Path(part["path"])
            doc = by_path.get(str(path.resolve()))
            if (
                not doc
                or not doc.approved
                or doc.active_revision < 1
                or doc.content_sha256 != part["sha256"]
                or digest(path) != part["sha256"]
            ):
                raise ValueError("LEGACY_PREPARATION_PART_CHECKSUM")
            expected = list(chunk_segments(load(path, settings)))
            actual = list(
                db.scalars(
                    select(Chunk)
                    .where(Chunk.document_id == doc.id, Chunk.revision == doc.active_revision)
                    .order_by(Chunk.ordinal)
                )
            )

            def signature(x):
                return x.text, x.heading_path, x.page_start, x.page_end

            if [signature(c) for c in expected] != [signature(c) for c in actual]:
                raise ValueError("LEGACY_PREPARATION_CHUNK_MISMATCH")
            data = json.loads(path.read_text(encoding="utf-8"))
            for page in data["pages"]:
                mode = page.get("metadata", {}).get(
                    "extraction", data["metadata"].get("extraction")
                )
                if mode == "PDF_EMBEDDED_TEXT" and page["text"] != re.sub(
                    r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", pdf[page["page"] - 1].get_text()
                ):
                    raise ValueError("LEGACY_PREPARATION_SOURCE_TEXT_MISMATCH")
    if apply:
        db.refresh(book, with_for_update=True)
        if (
            not book.approved
            or book.active_generation != generation
            or book.source_sha256 != row["sha256"]
            or book.preparation_sha256
        ):
            raise ValueError("LEGACY_PREPARATION_CHANGED_DURING_VERIFY")
        book.preparation_sha256 = preparation_identity(state)
        db.commit()
    return {
        "id": row["id"],
        "verified": True,
        "applied": apply,
        "preserved_generation": generation,
        "preserved_documents": len(documents),
    }
