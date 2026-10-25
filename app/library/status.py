"""Synchronize derived library status from active database rows, never filenames."""

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.library.catalog import atomic_json, catalog_lock, digest, read_catalog


def sync_status(db, output: Path, *, verify_originals=False):
    with catalog_lock(output):
        catalog = read_catalog(output / "library.json")
        books = {
            str(r["id"]): dict(r)
            for r in db.execute(text("SELECT * FROM library_books")).mappings()
        }
        counts = {
            str(r["book_id"]): dict(r)
            for r in db.execute(
                text("""
                SELECT b.id AS book_id, count(DISTINCT d.id) AS parts,
                    count(DISTINCT c.id) AS chunks, count(e.chunk_id) AS vector_rows,
                    min(d.local_path) AS active_part_path
                FROM library_books b JOIN documents d ON d.book_id=b.id
                    AND d.book_generation=b.active_generation AND d.approved
                JOIN chunks c ON c.document_id=d.id AND c.revision=d.active_revision
                LEFT JOIN chunk_embeddings e ON e.chunk_id=c.id AND e.identity=d.embedding_identity
                WHERE b.approved AND b.active_generation>0
                GROUP BY b.id
            """)
            ).mappings()
        }
        resources = catalog["resources"] + catalog.get("virtual_books", [])
        snapshots = {}
        original_checks = []
        for row in resources:
            book = books.get(row["id"])
            if (
                verify_originals
                and row["format"] == "pdf"
                and Path(row["root"]).name == "Knowledge"
                and not row.get("parent_resource_id")
            ):
                source = Path(row["absolute_path"])
                original_checks.append(
                    {
                        "id": row["id"],
                        "unchanged": source.exists()
                        and digest(source) == row["sha256"]
                        and source.stat().st_size == row["size_bytes"]
                        and source.stat().st_mtime_ns == row["mtime_ns"],
                    }
                )
            if not book:
                continue
            count = counts.get(row["id"], {})
            ready = (
                book["approved"]
                and book["status"] in {"INDEXED", "PARTIALLY_INDEXED"}
                and count.get("chunks", 0) > 0
            )
            status = book["status"]
            if status in {"INDEXED", "PARTIALLY_INDEXED"} and not ready:
                status = "INDEX_FAILED"
            state_file = (
                output
                / "ingestion-cache"
                / row["id"]
                / row["sha256"]
                / "bookparts-v2"
                / "preparation.json"
            )
            if count.get("active_part_path"):
                state_file = Path(count["active_part_path"]).parent / "preparation.json"
            state = (
                json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
            )
            snapshot = {
                "status": status,
                "retrievable": bool(ready),
                "source_sha256": book["source_sha256"],
                "source_matches_catalog": book["source_sha256"] == row["sha256"],
                "indexed_revision": book["active_generation"],
                "parts": count.get("parts", 0),
                "chunks": count.get("chunks", 0),
                "vector_rows": count.get("vector_rows", 0),
                "parser_version": "bookparts-v2"
                if state_file.parent.name == "bookparts-v2"
                else "bookparts-v1",
                "collection": row["collection"],
                "pdf_pages": state.get("total_pdf_pages") or 0,
                "ocr_pages": state.get("ocr_pages", []),
                "unresolved_pages": state.get("ocr_required_pages", []),
                "blank_pages": state.get("blank_pages", []),
            }
            snapshots[row["id"]] = snapshot
            row["ingestion"] = snapshot
        summary = {
            "physical_catalog_resources": len(catalog["resources"]),
            "virtual_references": len(catalog.get("virtual_books", [])),
            "retrievable_references": sum(s["retrievable"] for s in snapshots.values()),
            "states": dict(Counter(s["status"] for s in snapshots.values())),
            "collections": dict(
                Counter(s["collection"] for s in snapshots.values() if s["retrievable"])
            ),
            "active_parts": sum(s["parts"] for s in snapshots.values() if s["retrievable"]),
            "active_chunks": sum(s["chunks"] for s in snapshots.values() if s["retrievable"]),
            "active_vectors": sum(s["vector_rows"] for s in snapshots.values() if s["retrievable"]),
            "pdf_pages_in_prepared_references": sum(s["pdf_pages"] for s in snapshots.values()),
            "ocr_pages": sum(len(s["ocr_pages"]) for s in snapshots.values()),
            "unresolved_pages": sum(len(s["unresolved_pages"]) for s in snapshots.values()),
        }
        when = datetime.now(UTC).isoformat()
        atomic_json(output / "library.json", catalog)
        atomic_json(
            output / "ingestion-status.json",
            {
                "derived_from": "active Knowledge DB rows and preparation checkpoints",
                "updated_at": when,
                "summary": summary,
                "resources": snapshots,
            },
        )
        if verify_originals:
            atomic_json(
                output / "reports" / "original-file-audit.json",
                {
                    "checked_at": when,
                    "results": original_checks,
                    "all_unchanged": all(r["unchanged"] for r in original_checks),
                },
            )
        coverage_path = output / "social-roadmap-coverage.json"
        if coverage_path.exists():
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            for reading in coverage["readings"]:
                states = [snapshots.get(i, {}) for i in reading["resource_ids"]]
                # CORE HTML readings are multi-page resources; require all collected pages.
                reading["indexed"] = bool(states) and all(
                    s.get("retrievable", False) for s in states
                )
                reading["partial_extraction"] = any(
                    s.get("status") == "PARTIALLY_INDEXED" for s in states
                )
                reading["index_note"] = (
                    "Active DB verified; partial means unreadable pages excluded. Title matches do not certify complete editions."
                )
            coverage["indexed_readings"] = sum(r["indexed"] for r in coverage["readings"])
            coverage["updated_at"] = when
            atomic_json(coverage_path, coverage)
            with (output / "social-roadmap-coverage.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                fields = [
                    "phase",
                    "reading",
                    "availability",
                    "indexed",
                    "partial_extraction",
                    "resource_ids",
                ]
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(
                    {**r, "resource_ids": "; ".join(r["resource_ids"])}
                    for r in coverage["readings"]
                )
        return summary
