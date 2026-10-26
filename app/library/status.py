"""Synchronize derived library status from active database rows, never filenames."""

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.library.catalog import atomic_json, catalog_lock, digest, read_catalog
from app.library.books import (
    preparation_folder,
    preparation_identity,
    non_text_preparation,
    require_shared_permission,
)
from app.library.source import verify_source


def active_preparation(output, row, identity, source_sha, active_part_path=None):
    desired = preparation_folder(output / "ingestion-cache", row) / "preparation.json"
    root = output / "ingestion-cache" / row["id"] / source_sha
    candidates = [desired]
    if active_part_path:
        candidates.append(Path(active_part_path).parent / "preparation.json")
    candidates += [root / "preparation.json", *root.glob("bookparts-v*/preparation.json")]
    for path in dict.fromkeys(candidates):
        if not path.exists():
            continue
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("complete") and (
            preparation_identity(state) == identity
            or identity is None
            and active_part_path
            and path.parent == Path(active_part_path).parent
        ):
            return path, state
    return desired, {}


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
            if verify_originals and row["format"] == "pdf" and not row.get("parent_resource_id"):
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
                if row["format"] == "pdf" and row.get("preparation_version") == 3:
                    path = preparation_folder(output / "ingestion-cache", row) / "preparation.json"
                    if path.exists():
                        state = json.loads(path.read_text(encoding="utf-8"))
                        if non_text_preparation(row, state):
                            require_shared_permission(row)
                            verify_source(row)
                            snapshot = {
                                "status": "REVIEWED_NON_TEXT",
                                "retrievable": False,
                                "processed_non_text": True,
                                "source_sha256": row["sha256"],
                                "source_matches_catalog": True,
                                "preparation_verified": True,
                                "preparation_path": str(path),
                                "preparation_identity": preparation_identity(state),
                                "collection": row["collection"],
                                "parts": 0,
                                "chunks": 0,
                                "vector_rows": 0,
                                "pdf_pages": state["total_pdf_pages"],
                                "blank_pages": state["blank_pages"],
                                "reviewed_non_text_pages": state.get("reviewed_non_text_pages", []),
                                "unresolved_pages": [],
                                "ocr_pages": [],
                            }
                            snapshots[row["id"]] = snapshot
                            row["ingestion"] = snapshot
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
            state_file, state = active_preparation(
                output,
                row,
                book["preparation_sha256"],
                book["source_sha256"] or row["sha256"],
                count.get("active_part_path"),
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
                "parser_version": state_file.parent.name
                if state_file.parent.name.startswith("bookparts-v")
                else "bookparts-v1",
                "preparation_path": str(state_file) if state else None,
                "preparation_verified": bool(state and book["preparation_sha256"]),
                "collection": row["collection"],
                "pdf_pages": state.get("total_pdf_pages") or 0,
                "ocr_pages": state.get("ocr_pages", []),
                "unresolved_pages": state.get("ocr_required_pages", []),
                "blank_pages": state.get("blank_pages", []),
                "reviewed_non_text_pages": state.get("reviewed_non_text_pages", []),
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
        compilations = {}
        for parent in catalog["resources"]:
            if parent.get("mba_text_reuse"):
                continue
            registered = [
                r
                for r in catalog.get("virtual_books", [])
                if r.get("parent_resource_id") == parent["id"]
            ]
            if not registered:
                continue
            children = [
                r
                for r in registered
                if r["sha256"] == parent["sha256"]
                and snapshots.get(r["id"], {}).get("retrievable")
                and snapshots.get(r["id"], {}).get("source_matches_catalog")
                and snapshots.get(r["id"], {}).get("preparation_verified")
            ]
            ranges = sorted(r["page_range"] for r in children)
            covered = 0
            end = 0
            overlaps = 0
            for first, last in ranges:
                overlaps += max(0, min(end, last) - first + 1)
                covered += max(0, last - max(first, end + 1) + 1)
                end = max(end, last)
            unresolved = sorted(
                {p for r in children for p in snapshots[r["id"]]["unresolved_pages"]}
            )
            total = parent["pdf_pages"]
            aggregate = {
                "status": "REVOKED"
                if parent["rights"]["permission_status"] == "REVOKED"
                else "INDEXED_VIA_RANGES"
                if covered == total and not unresolved
                else "PARTIALLY_INDEXED_VIA_RANGES"
                if covered == total
                else "PROCESSING_VIA_RANGES",
                "source_sha256": parent["sha256"],
                "physical_pdf_pages": total,
                "active_range_references": len(children),
                "processed_physical_pages": covered,
                "remaining_physical_pages": total - covered,
                "overlapping_page_references": overlaps,
                "unresolved_pages": unresolved,
                "retrievable_directly": False,
            }
            parent["ingestion"] = aggregate
            compilations[parent["id"]] = aggregate
        mba_reuse = {}
        document_state = {
            str(r["id"]): dict(r)
            for r in db.execute(
                text("""
                SELECT d.id,d.approved,d.active_revision,d.content_sha256,
                    d.embedding_identity, count(c.id) AS chunks,
                    count(e.chunk_id) AS vectors
                FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
                    AND c.revision=d.active_revision
                LEFT JOIN chunk_embeddings e ON e.chunk_id=c.id
                    AND e.identity=d.embedding_identity
                WHERE d.book_id IS NULL GROUP BY d.id
                """)
            ).mappings()
        }
        for parent in catalog["resources"]:
            evidence = parent.get("mba_text_reuse")
            if not evidence:
                continue
            linked = evidence["document_ids"]
            valid = (
                bool(linked)
                and (
                    set(evidence.get("document_proofs", {})) == set(linked)
                    and evidence["source_sha256"] == parent["sha256"]
                )
                and all(
                    document_state.get(identifier, {}).get("approved")
                    and document_state[identifier]["active_revision"] > 0
                    and document_state[identifier]["chunks"] > 0
                    and document_state[identifier]["vectors"]
                    == document_state[identifier]["chunks"]
                    and all(
                        document_state[identifier][field] == expected
                        for field, expected in evidence.get("document_proofs", {})
                        .get(identifier, {})
                        .items()
                    )
                    for identifier in linked
                )
            )
            children = [
                r
                for r in catalog.get("virtual_books", [])
                if r.get("mba_page_supplement") and r.get("parent_resource_id") == parent["id"]
            ]
            ready = [
                r
                for r in children
                if (
                    snapshots.get(r["id"], {}).get("retrievable")
                    or snapshots.get(r["id"], {}).get("processed_non_text")
                )
                and snapshots.get(r["id"], {}).get("source_matches_catalog")
                and snapshots.get(r["id"], {}).get("preparation_verified")
            ]
            unresolved = sorted({p for r in ready for p in snapshots[r["id"]]["unresolved_pages"]})
            complete = (
                valid
                and len(ready) == len(children)
                and sorted(r["page_range"] for r in children)
                == sorted(evidence["supplement_ranges"])
            )
            status = (
                "REVOKED"
                if parent["rights"]["permission_status"] == "REVOKED"
                else "INDEXED_TEXT_VIA_EXISTING_MBA"
                if complete and not unresolved
                else "PARTIALLY_INDEXED_MBA_TEXT"
                if complete
                else "EXISTING_MBA_TEXT_PENDING_SUPPLEMENTS"
                if valid
                else "MBA_EXISTING_TEXT_REAUDIT_REQUIRED"
            )
            snapshot = {
                "status": status,
                "retrievable": bool(complete and status != "REVOKED"),
                "source_sha256": parent["sha256"],
                "source_matches_catalog": bool(valid),
                "existing_document_ids": linked,
                "supplement_references": len(children),
                "active_supplement_references": len(ready),
                "unresolved_pages": unresolved,
                "note": evidence["graphic_interpretation"],
            }
            parent["ingestion"] = snapshot
            mba_reuse[parent["id"]] = snapshot
        summary["mba_original_pdfs_reusing_existing_text"] = len(mba_reuse)
        summary["mba_original_pdfs_complete_with_supplements"] = sum(
            s["status"] == "INDEXED_TEXT_VIA_EXISTING_MBA" for s in mba_reuse.values()
        )
        when = datetime.now(UTC).isoformat()
        atomic_json(output / "library.json", catalog)
        atomic_json(
            output / "ingestion-status.json",
            {
                "derived_from": "active Knowledge DB rows and preparation checkpoints",
                "updated_at": when,
                "summary": summary,
                "resources": snapshots,
                "compilations": compilations,
                "mba_text_reuse": mba_reuse,
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
