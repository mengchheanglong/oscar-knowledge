"""Verify embedded-text cache pages against original PDFs; gate mismatches off."""

import json
import hashlib
import re
from pathlib import Path

import pymupdf
from sqlalchemy import select

from app.db.models import Document, LibraryBook
from app.db.session import session
from app.library.catalog import atomic_json, digest, read_catalog
from app.library.source import verify_source

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def prior_page_hashes(previous, documents, source_sha256):
    """Recover only text hashes already proved against the same original bytes."""
    if (
        previous.get("status") != "PASS"
        or previous.get("proof", {}).get("source_sha256") != source_sha256
    ):
        return {}
    result = {}
    for identifier, revision, sha in previous["proof"]["parts"]:
        document = documents.get(identifier)
        if not document or document.active_revision != revision:
            continue
        path = Path(document.local_path)
        if not path.exists() or digest(path) != sha:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for page in data["pages"]:
            mode = page.get("metadata", {}).get("extraction", data["metadata"].get("extraction"))
            if mode == "PDF_EMBEDDED_TEXT":
                result[page["page"]] = hashlib.sha256(page["text"].encode()).hexdigest()
    return result


def main():
    catalog = read_catalog(ROOT / "library.json")
    resources = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}
    report_path = ROOT / "reports" / "extraction-audit.json"
    prior = (
        {r["id"]: r for r in json.loads(report_path.read_text(encoding="utf-8"))["results"]}
        if report_path.exists()
        else {}
    )
    results = []
    verified_sources = set()
    with session() as db:
        books = list(db.scalars(select(LibraryBook).where(LibraryBook.active_generation > 0)))
        document_lookup = {
            str(d.id): d for d in db.scalars(select(Document).where(Document.book_id.is_not(None)))
        }
        verified_page_hashes = {}
        for previous in prior.values():
            sha = previous.get("proof", {}).get("source_sha256")
            if sha:
                verified_page_hashes.setdefault(sha, {}).update(
                    prior_page_hashes(previous, document_lookup, sha)
                )
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
            proof = {
                "source_sha256": book.source_sha256,
                "generation": book.active_generation,
                "preparation_sha256": book.preparation_sha256,
                "parts": sorted((str(d.id), d.active_revision, d.content_sha256) for d in docs),
            }
            # Reuse an earlier original-text comparison only after rehashing the
            # original and every identical active part. This does not cache an
            # unchecked file stat, approval, or database-text verification.
            previous = prior.get(str(book.id), {})
            if previous.get("status") == "PASS" and previous.get("proof") == json.loads(
                json.dumps(proof)
            ):
                for document in docs:
                    if digest(Path(document.local_path)) != document.content_sha256:
                        raise ValueError("AUDITED_PART_CHECKSUM_CHANGED")
                results.append({**previous, "reused_verified_source_comparison": True})
                print(
                    str(book.id),
                    "PASS_REVERIFIED_PARTS",
                    previous["checked_embedded_pages"],
                    flush=True,
                )
                continue
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
                        cached = verified_page_hashes.get(book.source_sha256, {}).get(page["page"])
                        matches = (
                            hashlib.sha256(page["text"].encode()).hexdigest() == cached
                            if cached
                            else page["text"]
                            == re.sub(
                                r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
                                " ",
                                source[page["page"] - 1].get_text(),
                            )
                        )
                        checked += 1
                        if not matches:
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
                    "proof": proof,
                    "reused_verified_source_comparison": False,
                }
            )
            print(
                str(book.id), "PASS" if not mismatches else "REPAIR_REQUIRED", checked, flush=True
            )
    atomic_json(
        report_path,
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
    if any(r["status"] != "PASS" for r in results):
        raise ValueError("ORIGINAL_TEXT_COMPARISON_FAILED")


if __name__ == "__main__":
    main()
