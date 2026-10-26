"""Verify embedded-text cache pages against original PDFs; gate mismatches off."""

import json
import re
from pathlib import Path

import pymupdf
from sqlalchemy import select

from app.db.models import Document, LibraryBook
from app.db.session import session
from app.library.catalog import atomic_json, digest, read_catalog
from app.library.source import verify_source

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def main():
    catalog = read_catalog(ROOT / "library.json")
    resources = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}
    results = []
    verified_sources = set()
    with session() as db:
        books = list(db.scalars(select(LibraryBook).where(LibraryBook.active_generation > 0)))
        for book in books:
            row = resources.get(str(book.id))
            if not row or row["format"] != "pdf":
                continue
            if row["sha256"] != book.source_sha256:
                results.append({"id": str(book.id), "status": "SOURCE_CHANGED_NOT_AUDITED"})
                continue
            key = (row["absolute_path"], row["sha256"])
            verify_source(row, force=key not in verified_sources)
            verified_sources.add(key)
            mismatches = []
            checked = 0
            docs = list(
                db.scalars(
                    select(Document).where(
                        Document.book_id == book.id,
                        Document.book_generation == book.active_generation,
                    )
                )
            )
            with pymupdf.open(row["absolute_path"]) as source:
                for doc in docs:
                    data = json.loads(Path(doc.local_path).read_text(encoding="utf-8"))
                    assert digest(Path(doc.local_path)) == doc.content_sha256
                    for page in data["pages"]:
                        extraction = page.get("metadata", {}).get(
                            "extraction", data["metadata"].get("extraction")
                        )
                        if extraction != "PDF_EMBEDDED_TEXT":
                            continue
                        original = re.sub(
                            r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
                            " ",
                            source[page["page"] - 1].get_text(),
                        )
                        checked += 1
                        if page["text"] != original:
                            mismatches.append(page["page"])
            if mismatches:
                book.status = "REPAIR_REQUIRED"
                db.commit()
            results.append(
                {
                    "id": str(book.id),
                    "checked_embedded_pages": checked,
                    "mismatched_pages": mismatches,
                    "status": "REPAIR_REQUIRED" if mismatches else "PASS",
                }
            )
            print(
                str(book.id), "PASS" if not mismatches else "REPAIR_REQUIRED", checked, flush=True
            )
    atomic_json(
        ROOT / "reports" / "extraction-audit.json",
        {
            "results": results,
            "scope": "Embedded text exact comparison; OCR output remains machine extracted and requires visual/formula review.",
        },
    )
    print(
        "Verified books",
        len(results),
        "repair gates",
        sum(r["status"] == "REPAIR_REQUIRED" for r in results),
        "embedded pages",
        sum(r.get("checked_embedded_pages", 0) for r in results),
    )


if __name__ == "__main__":
    main()
