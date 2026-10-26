"""Field-level, source-bound correction of the historical Gemini metadata pass.

Default is preview. --apply saves catalog changes; --activate additionally stages
and ingests changed private notices through the existing whole-book pipeline.
Never writes shared baseline documents or overwrites old preparations.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.db.models import LibraryBook
from app.db.session import session
from app.library.books import ingest_parts, prepare
from app.library.catalog import atomic_json, catalog_lock, read_catalog

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")
HISTORICAL = ROOT / "reports/quality-review/2026-10-26"
OUTPUT = HISTORICAL / "corrected"


def corrected_note(current, previous, baseline, reviewed):
    """Revert only the exact erroneous field; concurrent user edits are conflicts."""
    if current not in {previous, baseline} and current != reviewed:
        raise ValueError("QUALITY_METADATA_CONFLICT")
    return reviewed if reviewed is not None else baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    if args.activate and not args.apply:
        parser.error("--activate requires --apply")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    historical = json.loads((HISTORICAL / "REPAIR_MANIFEST.json").read_text(encoding="utf-8"))
    backup = read_catalog(HISTORICAL / "library.json.pre-repair.bak")
    originals = {r["id"]: r for r in backup["resources"] + backup.get("virtual_books", [])}
    reviews = json.loads(
        (OUTPUT / "SOURCE_CLASSIFICATION_REVIEWS.json").read_text(encoding="utf-8")
    )
    reviewed = {r["resource_id"]: r for r in reviews["reviews"]}
    receipts = []
    pending = []
    with catalog_lock(ROOT):
        catalog = read_catalog(ROOT / "library.json")
        rows = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}
        with session() as db:
            for old in historical["repairs_applied"]:
                identifier = old["resource_id"]
                row, before = rows[identifier], originals[identifier]
                if row["sha256"] != old["source_checksum"] or before["sha256"] != row["sha256"]:
                    raise ValueError("QUALITY_SOURCE_CHANGED")
                baseline = (before.get("metadata") or {}).get("coverage_note")
                metadata = row.setdefault("metadata", {})
                review = reviewed.get(identifier)
                if review and (
                    review["source_sha256"] != row["sha256"]
                    or review["review_status"] != "REVIEWED"
                ):
                    raise ValueError("QUALITY_REVIEW_SOURCE_CHANGED")
                desired = review["notice"] if review else None
                note = corrected_note(
                    metadata.get("coverage_note"), old.get("new_value"), baseline, desired
                )
                old_note = metadata.get("coverage_note")
                if note is None:
                    metadata.pop("coverage_note", None)
                else:
                    metadata["coverage_note"] = note
                if review:
                    metadata["representation_review"] = review
                book = db.get(LibraryBook, identifier)
                notice_changed = False
                # Shared MBA reuse keeps its current approved documents untouched.
                if review and book and book.active_generation and book.visibility == "PRIVATE":
                    base_notice = before.get("source_notice") or ""
                    notice = " ".join(filter(None, [base_notice, desired]))
                    if len(notice) > 300:
                        raise ValueError("SOURCE_NOTICE_TOO_LONG")
                    if row.get("source_notice") != notice:
                        row["source_notice"] = notice
                        row["preparation_revision"] = row.get("preparation_revision", 0) + 1
                        notice_changed = True
                    pending.append(row)
                receipts.append(
                    {
                        "resource_id": identifier,
                        "source_sha256": row["sha256"],
                        "old_note": old_note,
                        "new_note": note,
                        "notice_changed": notice_changed,
                        "classification": review["classification"]
                        if review
                        else "RETRACTED_UNSUPPORTED_COMMERCIAL_LABEL",
                        "status": "PENDING_ACTIVATION" if notice_changed else "CATALOG_ONLY",
                    }
                )
        if args.apply:
            atomic_json(ROOT / "library.json", catalog)
    results = []
    if args.activate:
        for resource in pending:
            prepared = prepare(resource, ROOT / "ingestion-cache", whole_book=True)
            with session() as db:
                result = ingest_parts(
                    db, resource, prepared, resource["collection"], get_settings(), limit=100
                )
            if result["status"] != "INDEXED":
                raise ValueError("QUALITY_ACTIVATION_INCOMPLETE")
            results.append({"resource_id": resource["id"], **result})
    manifest = {
        "checked_at": datetime.now(UTC).isoformat(),
        "applied": args.apply,
        "changes": receipts,
        "activations": results,
        "scope": "Five source covers reviewed; catalog field repair is not full-book semantic verification.",
        "rollback": "Use recorded old fields and retained preparation generations; never restore the whole historical catalog over concurrent changes.",
    }
    atomic_json(
        OUTPUT / ("REPAIR_MANIFEST.json" if args.apply else "REPAIR_PREVIEW.json"), manifest
    )
    print(
        json.dumps(
            {
                "applied": args.apply,
                "resources_checked": len(receipts),
                "active_private_notices": len(pending),
                "activations": len(results),
            }
        )
    )


if __name__ == "__main__":
    main()
