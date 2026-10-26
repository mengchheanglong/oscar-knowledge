"""Check every processed PDF page has an explicit outcome and every text page has active chunks."""

import json
import argparse
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db.models import Chunk, Document, LibraryBook
from app.db.session import session
from app.library.catalog import atomic_json, digest, read_catalog
from app.library.books import preparation_identity
from app.library.status import sync_status

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-complete", action="store_true")
    arguments = parser.parse_args()
    with session() as db:
        sync_status(db, ROOT)
        indexed_pages = defaultdict(set)
        for book, page in db.execute(
            select(Document.book_id, Chunk.page_start)
            .join(Chunk, Chunk.document_id == Document.id)
            .join(LibraryBook, Document.book_id == LibraryBook.id)
            .where(
                LibraryBook.approved.is_(True),
                LibraryBook.active_generation == Document.book_generation,
                Chunk.revision == Document.active_revision,
                Chunk.page_start.is_not(None),
            )
            .distinct()
        ):
            indexed_pages[str(book)].add(page)
        identities = {str(b.id): b.preparation_sha256 for b in db.scalars(select(LibraryBook))}
    catalog = read_catalog(ROOT / "library.json")
    status = json.loads((ROOT / "ingestion-status.json").read_text(encoding="utf-8"))
    results = []
    for row in catalog["resources"] + catalog.get("virtual_books", []):
        snapshot = status["resources"].get(row["id"], {})
        if row["format"] != "pdf" or not (
            snapshot.get("retrievable") or snapshot.get("processed_non_text")
        ):
            continue
        state = json.loads(Path(snapshot["preparation_path"]).read_text(encoding="utf-8"))
        expected = set(
            range(
                row.get("page_range", [1])[0], row.get("page_range", [1, row["pdf_pages"]])[-1] + 1
            )
        )
        actual = set()
        duplicates = set()
        checksums = True
        for part in state["parts"]:
            path = Path(part["path"])
            checksums &= digest(path) == part["sha256"]
            for page in json.loads(path.read_text(encoding="utf-8"))["pages"]:
                if page["page"] in actual:
                    duplicates.add(page["page"])
                actual.add(page["page"])
        outcomes = (
            list(actual)
            + state["blank_pages"]
            + state.get("reviewed_non_text_pages", [])
            + state["ocr_required_pages"]
        )
        covered = set(outcomes)
        missing = sorted(expected - covered)
        extra = sorted(covered - expected)
        duplicate_outcomes = len(outcomes) != len(covered)
        missing_chunks = sorted(actual - indexed_pages[row["id"]])
        unexpected_chunks = sorted(indexed_pages[row["id"]] - actual)
        valid = (
            state["complete"]
            and checksums
            and preparation_identity(state)
            == identities.get(row["id"], snapshot.get("preparation_identity"))
            and not (
                missing
                or extra
                or duplicates
                or duplicate_outcomes
                or missing_chunks
                or unexpected_chunks
            )
        )
        results.append(
            {
                "id": row["id"],
                "status": "PASS" if valid else "FAIL",
                "physical_pages": len(expected),
                "text_pages_with_active_chunks": len(actual),
                "blank_pages": len(state["blank_pages"]),
                "reviewed_non_text_pages": len(state.get("reviewed_non_text_pages", [])),
                "unresolved_pages": state["ocr_required_pages"],
                "missing_pages": missing,
                "extra_pages": extra,
                "missing_chunk_pages": missing_chunks,
                "unexpected_chunk_pages": unexpected_chunks,
                "duplicate_outcomes": duplicate_outcomes,
                "part_checksums_valid": checksums,
            }
        )
    report = {
        "results": results,
        "compilations": status.get("compilations", {}),
        "scope": "Complete processing outcomes are distinct from successful interpretation of every graphic or OCR symbol.",
    }
    physical_pdfs = [r for r in catalog["resources"] if r["format"] == "pdf"]
    pending = [
        r["id"]
        for r in physical_pdfs
        if r.get("ingestion", {}).get("status")
        not in {
            "INDEXED",
            "INDEXED_VIA_RANGES",
            "INDEXED_TEXT_VIA_EXISTING_MBA",
            "REVIEWED_NON_TEXT",
        }
    ]
    report["original_pdf_completion"] = {
        "physical_files": len(physical_pdfs),
        "physical_pages": sum(r["pdf_pages"] for r in physical_pdfs),
        "completed_files": len(physical_pdfs) - len(pending),
        "pending_resource_ids": pending,
    }
    atomic_json(ROOT / "reports" / "page-coverage-audit.json", report)
    failures = sum(r["status"] != "PASS" for r in results)
    print(
        "PDF references checked",
        len(results),
        "physical pages",
        sum(r["physical_pages"] for r in results),
        "failures",
        failures,
        "unresolved pages",
        sum(len(r["unresolved_pages"]) for r in results),
    )
    if failures:
        raise ValueError("PDF_PAGE_COVERAGE_AUDIT_FAILED")
    if arguments.require_complete and (pending or any(r["unresolved_pages"] for r in results)):
        raise ValueError("ORIGINAL_PDF_COMPLETION_PENDING")


if __name__ == "__main__":
    main()
