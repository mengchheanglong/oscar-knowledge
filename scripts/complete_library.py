"""Gap-free compilation registration and finite concurrent private ingestion.

Range titles describe physical pages, not inferred book editions. Original files
and existing logical roadmap identities are retained. Local model calls remain
serialized by the existing inference semaphore; threads overlap extraction/DB IO.
"""

import argparse
import concurrent.futures
import json
import threading
import time
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db.models import LibraryBook
from app.db.session import session
from app.library.books import (
    ingest_parts,
    non_text_preparation,
    preparation_folder,
    preparation_identity,
    prepare,
    require_shared_permission,
)
from app.library.catalog import atomic_json, catalog_lock, read_catalog
from app.library.source import verify_source

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def uncovered_windows(total, intervals, size=1000):
    cursor = 1
    result = []
    for first, last in sorted(intervals) + [(total + 1, total + 1)]:
        if first < cursor or first > last or last > total + 1:
            raise ValueError("COMPILATION_RANGE_OVERLAP_OR_BOUNDS")
        while cursor < first:
            end = min(cursor + size - 1, first - 1)
            result.append([cursor, end])
            cursor = end + 1
        cursor = last + 1
    return result


def register(output):
    with catalog_lock(output):
        value = read_catalog(output / "library.json")
        parent = next(r for r in value["resources"] if "All_119_OPENSTAX" in r["filename"])
        require_shared_permission(parent)
        verify_source(parent, force=True)
        reviewed = json.loads(
            (output / "compilation-reviewed-ranges.json").read_text(encoding="utf-8")
        )
        if (
            reviewed["source_sha256"] != parent["sha256"]
            or reviewed["parent_resource_id"] != parent["id"]
        ):
            raise ValueError("COMPILATION_RANGE_REVIEW_CHECKSUM_CHANGED")
        selected = [
            r
            for r in value.get("virtual_books", [])
            if r.get("parent_resource_id") == parent["id"] and not r.get("compilation_window")
        ]
        # Previously inspected original pages establish the Political Science
        # endpoint. The old outline-only endpoint included unrelated inserted books.
        review = reviewed["ranges"]["political"]
        political = next(r for r in selected if r["id"] == review["id"])
        political.update(
            page_range=review["page_range"],
            pdf_pages=review["page_range"][1] - review["page_range"][0] + 1,
            preparation_version=3,
            source_range_evidence="Cover, chapter sequence and final Index page physically inspected; next pages are unrelated material. Corrected 2026-10-26.",
        )
        windows = uncovered_windows(parent["pdf_pages"], [r["page_range"] for r in selected])
        prior = {r["id"]: r for r in value.get("virtual_books", [])}
        registered = []
        for first, last in windows:
            identifier = str(uuid.uuid5(uuid.UUID(parent["id"]), f"coverage-v1:{first}:{last}"))
            row = {
                **parent,
                "id": identifier,
                "parent_resource_id": parent["id"],
                "compilation_window": True,
                "page_range": [first, last],
                "pdf_pages": last - first + 1,
                "title": f"Mixed local compilation — PDF pages {first}–{last}",
                "authors": [],
                "edition": None,
                "publication_year": None,
                "collection": "personal-library",
                "category": "mixed-reference",
                "tags": ["mixed-compilation", "outline-attribution-unverified"],
                "outline_level": 0,
                "preparation_version": 3,
                "metadata_status": "RANGE_LOCATOR_VERIFIED_BOOK_ATTRIBUTION_UNVERIFIED",
                "source_notice": "Mixed compilation; book/author attribution unverified. Cite physical PDF pages and treat claims as source perspectives.",
                "source_range_evidence": "Deterministic physical-page window, not a claimed book boundary",
                "ingestion": prior.get(identifier, {}).get("ingestion", {"status": "CATALOGED"}),
            }
            previous = prior.get(identifier, {})
            if previous.get("sha256") == parent["sha256"]:
                for field in [
                    "page_reviews",
                    "preparation_revision",
                    "physical_page_buckets",
                    "rights",
                    "access",
                    "metadata_status",
                    "authors",
                    "edition",
                    "publication_year",
                    "title",
                    "tags",
                    "category",
                    "source_notice",
                ]:
                    if field in previous:
                        row[field] = previous[field]
            registered.append(row)
        value["virtual_books"] = [
            r for r in value.get("virtual_books", []) if not r.get("compilation_window")
        ] + registered
        atomic_json(output / "library.json", value)
        plan = {
            "parent_resource_id": parent["id"],
            "source_sha256": parent["sha256"],
            "physical_pdf_pages": parent["pdf_pages"],
            "existing_roadmap_ranges": [
                {"id": r["id"], "page_range": r["page_range"]} for r in selected
            ],
            "remaining_windows": [
                {"id": r["id"], "page_range": r["page_range"]} for r in registered
            ],
            "registered_page_coverage": sum(r["pdf_pages"] for r in selected + registered),
            "note": "Gap-free physical coverage; nested outline nodes are not verified distinct books. Mixed non-OpenStax material exists.",
        }
        assert plan["registered_page_coverage"] == parent["pdf_pages"]
        atomic_json(output / "compilation-coverage-plan.json", plan)
    print(
        "Registered remaining windows",
        len(registered),
        "physical pages",
        plan["registered_page_coverage"],
        flush=True,
    )


def run(output, workers, limit, *, prepare_only=False, resource_kind="all"):
    settings = get_settings()
    target = make_url(settings.database_url)
    if (
        target.host not in {"127.0.0.1", "localhost"}
        or target.port != 43114
        or target.database != "knowledge"
        or settings.embedding_provider != "ollama"
    ):
        raise ValueError("LOCAL_KNOWLEDGE_AND_EMBEDDINGS_REQUIRED")
    catalog = read_catalog(output / "library.json")
    with session() as db:
        books = {str(b.id): b for b in db.scalars(select(LibraryBook))}
    rows = []
    for row in catalog["resources"] + catalog.get("virtual_books", []):
        if resource_kind == "mba" and Path(row["root"]) != Path("D:/AI/OSCAR/mba-corpus"):
            continue
        if resource_kind == "reviewed":
            active = books.get(row["id"])
            if not (
                row.get("page_reviews")
                and active
                and active.approved
                and active.status in {"INDEXED", "PARTIALLY_INDEXED"}
                and active.source_sha256 == row["sha256"]
            ):
                continue
        if (
            row.get("preparation_version") != 3
            or row["rights"].get("permission_status") != "APPROVED"
            or row["access"]["visibility"] != "PRIVATE"
        ):
            continue
        book = books.get(row["id"])
        checkpoint = preparation_folder(output / "ingestion-cache", row) / "preparation.json"
        prepared_identity = None
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            if state.get("complete"):
                prepared_identity = preparation_identity(state)
                if prepare_only:
                    require_shared_permission(row)
                    verify_source(row)
                    continue
                if not prepare_only and non_text_preparation(row, state):
                    require_shared_permission(row)
                    verify_source(row)
                    continue
        if (
            book
            and book.approved
            and book.status in {"INDEXED", "PARTIALLY_INDEXED"}
            and book.source_sha256 == row["sha256"]
            and book.preparation_sha256 == prepared_identity
        ):
            continue
        rows.append(row)
    rows.sort(key=lambda r: (bool(r.get("compilation_window")), r.get("page_range", [0])[0]))
    rows = rows[:limit]
    receipt = output / (
        "mba-preparation-2026-10-26.json"
        if prepare_only
        else "completion-mba-2026-10-26.json"
        if resource_kind == "mba"
        else "completion-reviewed-2026-10-26.json"
        if resource_kind == "reviewed"
        else "completion-2026-10-26.json"
    )
    results = (
        json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {"resources": {}}
    )
    lock = threading.Lock()

    def failure(error):
        import re

        code = str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else "LIBRARY_PROCESSING_FAILED"
        return {"status": "INDEX_FAILED", "error_code": code}

    def record(row, result, started):
        result["seconds"] = round(time.monotonic() - started, 2)
        with lock:
            results["resources"][row["id"]] = result
            atomic_json(receipt, results)
            print(
                row["id"],
                result["status"],
                result.get("chunks", 0),
                result.get("error_code", ""),
                result["seconds"],
                flush=True,
            )

    def prepare_row(row):
        started = time.monotonic()
        try:
            memory = 2 * 1024**3 if row.get("parent_resource_id") else 512 * 1024**2
            state = prepare(
                row, output / "ingestion-cache", page_batch=50, memory_bytes=memory, whole_book=True
            )
            while not state["complete"]:
                state = prepare(
                    row,
                    output / "ingestion-cache",
                    page_batch=50,
                    memory_bytes=memory,
                    whole_book=True,
                )
            if prepare_only:
                record(
                    row,
                    {"status": "PREPARED", "unresolved_pages": state["ocr_required_pages"]},
                    started,
                )
                return row, None, started
            return row, state, started
        except Exception as error:
            record(row, failure(error), started)
            return row, None, started

    def activate(row, state, started):
        try:
            if non_text_preparation(row, state):
                require_shared_permission(row)
                verify_source(row)
                record(row, {"status": "REVIEWED_NON_TEXT", "chunks": 0}, started)
                return
            transient = {"EMBEDDING_HTTP_ERROR", "EMBEDDING_UNAVAILABLE", "EMBEDDING_BUSY"}
            attempts = 0
            with session() as db:
                while True:
                    result = ingest_parts(
                        db, row, state, row["collection"], settings, limit=100, allow_partial=True
                    )
                    if result["status"] == "PROCESSING":
                        continue
                    if result.get("error_code") in transient and attempts < 2:
                        attempts += 1
                        time.sleep(1)
                        continue
                    break
            record(
                row,
                {
                    **result,
                    "unresolved_pages": state["ocr_required_pages"],
                    "ocr_pages": len(state["ocr_pages"]),
                    "reviewed_non_text_pages": state.get("reviewed_non_text_pages", []),
                },
                started,
            )
        except Exception as error:
            record(row, failure(error), started)

    # Two bounded preparation children can feed one serialized local inference
    # consumer. At most three prepared references wait for ingestion, so the GPU
    # need not idle while the next large PDF window is being extracted.
    iterator = iter(rows)
    with (
        concurrent.futures.ThreadPoolExecutor(max_workers=workers) as prep_pool,
        concurrent.futures.ThreadPoolExecutor(max_workers=1) as index_pool,
    ):
        pending = {
            prep_pool.submit(prepare_row, row)
            for row in [next(iterator, None) for _ in range(workers)]
            if row is not None
        }
        indexing = []
        while pending:
            done, pending = concurrent.futures.wait(
                pending, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                row, state, started = future.result()
                if state:
                    indexing.append(index_pool.submit(activate, row, state, started))
                    if len(indexing) >= 3:
                        indexing.pop(0).result()
                following = next(iterator, None)
                if following:
                    pending.add(prep_pool.submit(prepare_row, following))
        for future in indexing:
            future.result()
    verified_paths = set()
    for row in rows:
        if row["absolute_path"] not in verified_paths:
            verify_source(row, force=True)
            verified_paths.add(row["absolute_path"])
    failures = [
        r["id"]
        for r in rows
        if results["resources"].get(r["id"], {}).get("status")
        not in (
            {"PREPARED"} if prepare_only else {"INDEXED", "PARTIALLY_INDEXED", "REVIEWED_NON_TEXT"}
        )
    ]
    print(
        "Finite completion batch finished",
        len(rows),
        "failed references",
        len(failures),
        flush=True,
    )
    if failures:
        raise ValueError("LIBRARY_COMPLETION_BATCH_INCOMPLETE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", type=Path, default=ROOT)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resource-kind", choices=["all", "mba", "reviewed"], default="all")
    parser.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=2)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        raise ValueError("BOOK_BATCH_LIMIT")
    if args.register:
        register(args.catalog_dir)
    if args.run:
        run(
            args.catalog_dir,
            args.workers,
            args.limit,
            prepare_only=args.prepare_only,
            resource_kind=args.resource_kind,
        )
