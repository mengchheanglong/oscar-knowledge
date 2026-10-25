"""Bounded restartable local worker. Status is separate from discovery and rights."""

import argparse
import json
import time
from pathlib import Path

from app.config import get_settings
from app.db.session import session
from app.library.books import ingest_parts, prepare
from app.library.catalog import atomic_json, read_catalog

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--group", choices=["personal-library", "social-systems", "all"], default="all"
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--resource-id", action="append", default=[])
    parser.add_argument("--receipt", type=Path)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Expose extracted text with an explicit unresolved-page coverage notice",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        raise ValueError("BOOK_BATCH_LIMIT")
    catalog = read_catalog(ROOT / "library.json")
    from app.db.models import LibraryBook
    from sqlalchemy import select

    with session() as db:
        book_states = {
            str(b.id): (b.status, b.source_sha256) for b in db.scalars(select(LibraryBook))
        }
    rows = [
        r
        for r in catalog["resources"] + catalog.get("virtual_books", [])
        if r["rights"]["permission_status"] == "APPROVED"
        and r["access"]["visibility"] == "PRIVATE"
        and Path(r["root"]).name == "Knowledge"
        and (not args.resource_id or r["id"] in args.resource_id)
        and (args.group == "all" or r["collection"] == args.group)
    ]
    # Prepare real PDF books first, then supplementary HTML sections. Oversized
    # compilations remain explicit review items; never index their first N pages
    # and pretend that the rest of the file was consumed.
    receipt_path = args.receipt or ROOT / "ingestion-status.json"
    receipts = (
        json.loads(receipt_path.read_text())
        if receipt_path.exists()
        else {"derived_from": "Knowledge DB and preparation checkpoints", "resources": {}}
    )
    rows = [
        r
        for r in rows
        if book_states.get(r["id"], (None, None))[0] not in {"INDEXED", "PARTIALLY_INDEXED"}
        or book_states.get(r["id"], (None, None))[1] != r["sha256"]
    ]
    rows.sort(key=lambda r: (r["format"] != "pdf", r.get("pdf_pages") or 0, r["id"]))
    rows = rows[args.offset : args.offset + args.limit]
    settings = get_settings()
    from sqlalchemy.engine import make_url

    target = make_url(settings.database_url)
    if (
        target.host not in {"127.0.0.1", "localhost"}
        or target.port != 43114
        or target.database != "knowledge"
    ):
        raise ValueError("LOCAL_KNOWLEDGE_DATABASE_REQUIRED")
    for number, row in enumerate(rows, 1):
        started = time.monotonic()
        try:
            if row.get("pdf_pages", 0) and row["pdf_pages"] > 2000:
                raise ValueError("COMPILATION_RANGE_REVIEW_REQUIRED")
            state = prepare(row, ROOT / "ingestion-cache", page_batch=100)
            while not state["complete"]:
                state = prepare(row, ROOT / "ingestion-cache", page_batch=100)
            with session() as db:
                outcome = ingest_parts(
                    db,
                    row,
                    state,
                    row["collection"],
                    settings,
                    limit=100,
                    allow_partial=args.allow_partial,
                )
                while outcome["status"] == "PROCESSING":
                    outcome = ingest_parts(
                        db,
                        row,
                        state,
                        row["collection"],
                        settings,
                        limit=100,
                        allow_partial=args.allow_partial,
                    )
            result = {
                **outcome,
                "source_sha256": row["sha256"],
                "ocr_pages": state.get("ocr_pages", []),
                "ocr_required_pages": state["ocr_required_pages"],
                "blank_pages": state["blank_pages"],
                "parser_version": "bookparts-v2",
                "seconds": round(time.monotonic() - started, 2),
            }
        except Exception as error:
            import re

            code = (
                str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else "LIBRARY_PROCESSING_FAILED"
            )
            result = {
                "status": "OCR_REQUIRED" if "OCR" in code else "INDEX_FAILED",
                "error_code": code,
                "source_sha256": row["sha256"],
                "seconds": round(time.monotonic() - started, 2),
            }
        # Metadata stays in library.json. This small derived status view avoids
        # rewriting the complete 25,000-resource catalog after every part/book.
        receipts["resources"][row["id"]] = result
        atomic_json(receipt_path, receipts)
        print(
            number,
            row["id"],
            result["status"],
            result.get("chunks", 0),
            result.get("error_code", ""),
            flush=True,
        )
    print("Batch finished", len(rows), flush=True)


if __name__ == "__main__":
    main()
