"""Activate explicit source-image decisions; preserve raw PDFs and historical data.

Requires the private, manually reviewed decision packets. Finite and resumable;
no model-generated review labels and no automatic semantic certification.
"""

import copy
import json
import uuid
from pathlib import Path

from app.config import get_settings
from app.db.session import session
from app.library.books import ingest_parts, preparation_folder, prepare, require_shared_permission
from app.library.catalog import atomic_json, catalog_lock, digest, read_catalog
from app.library.review import stage_reviewed_pages

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")
OUTPUT = ROOT / "reports/quality-review/2026-10-26/corrected/source-review"
JOURNAL = OUTPUT / "APPLICATION_PLAN.json"
NOTICE = "Flagged pages use reviewed excerpts/descriptions with explicit errata, not full transcriptions."


def build_plan():
    decisions = json.loads((OUTPUT / "PAGE_REVIEW_DECISIONS.json").read_text(encoding="utf-8"))[
        "reviews"
    ]
    if len(decisions) != 68:
        raise ValueError("ALL_68_REVIEW_DECISIONS_REQUIRED")
    grouped = {}
    for number, review in decisions.items():
        if digest(OUTPUT / f"page-{int(number):02d}.png") != review["image_sha256"]:
            raise ValueError("REVIEW_IMAGE_CHANGED")
        grouped.setdefault(review["resource_id"], []).append(review)
    encoding = json.loads((OUTPUT / "ENCODING_REVIEW_DECISIONS.json").read_text(encoding="utf-8"))[
        "reviews"
    ]
    plan = {
        "resources": [],
        "shared_excluded_chunk_ids": [r["excluded_shared_chunk_id"] for r in encoding],
    }
    with catalog_lock(ROOT):
        catalog = read_catalog(ROOT / "library.json")
        rows = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}
        status = json.loads((ROOT / "ingestion-status.json").read_text(encoding="utf-8"))
        for identifier, reviews in grouped.items():
            row = rows[identifier]
            require_shared_permission(row)
            old_path = status["resources"][identifier]["preparation_path"]
            old = json.loads(Path(old_path).read_text(encoding="utf-8"))
            if row["sha256"] != reviews[0]["source_sha256"]:
                raise ValueError("REVIEW_SOURCE_CHANGED")
            if not row.get("source_review_completion_v1"):
                row["preparation_revision"] = row.get("preparation_revision", 0) + 1
                row["source_review_completion_v1"] = True
            row.setdefault("page_reviews", {}).update(
                {
                    str(r["physical_page"]): {
                        "classification": "VISUAL_DESCRIPTION",
                        "extraction": "VISUAL_DESCRIPTION",
                        "source_sha256": r["source_sha256"],
                        "text": r["text"],
                        "evidence": r["review_method"],
                        "review_scope": r["review_scope"],
                    }
                    for r in reviews
                }
            )
            if NOTICE not in (row.get("source_notice") or ""):
                row["source_notice"] = " ".join(filter(None, [row.get("source_notice"), NOTICE]))
            if len(row["source_notice"]) > 300:
                raise ValueError("NOTICE_LENGTH_EXCEEDED")
            plan["resources"].append(
                {"id": identifier, "previous": old, "reviews": reviews, "kind": "STAGED_REVIEW"}
            )
        for review in encoding:
            parent = rows[review["parent_resource_id"]]
            require_shared_permission(parent)
            if parent["sha256"] != review["source_sha256"]:
                raise ValueError("ENCODING_REVIEW_SOURCE_CHANGED")
            identifier = str(
                uuid.uuid5(
                    uuid.UUID(parent["id"]), f"reviewed-diagram-v1:{review['physical_page']}"
                )
            )
            if identifier not in rows:
                row = copy.deepcopy(parent)
                for key in list(row):
                    if key.startswith("mba_"):
                        del row[key]
                row.update(
                    id=identifier,
                    parent_resource_id=parent["id"],
                    quality_page_supplement=True,
                    title=parent["title"]
                    + f" — reviewed original PDF page {review['physical_page']}",
                    collection="personal-library",
                    page_range=[review["physical_page"]] * 2,
                    pdf_pages=1,
                    preparation_version=3,
                    preparation_revision=0,
                    outline_level=0,
                    source_notice="Reviewed source-page description; shared original text retained with its corrupted diagram chunks excluded.",
                    ingestion={"status": "CATALOGED"},
                    page_reviews={
                        str(review["physical_page"]): {
                            "source_sha256": parent["sha256"],
                            "classification": "VISUAL_DESCRIPTION",
                            "extraction": "VISUAL_DESCRIPTION",
                            "text": review["text"],
                            "evidence": review["review_method"],
                        }
                    },
                )
                catalog.setdefault("virtual_books", []).append(row)
            plan["resources"].append({"id": identifier, "kind": "PRIVATE_ENCODING_CORRECTION"})
        atomic_json(ROOT / "library.json", catalog)
        atomic_json(JOURNAL, plan)
    return plan


def main():
    plan = json.loads(JOURNAL.read_text(encoding="utf-8")) if JOURNAL.exists() else build_plan()
    for item in plan["resources"]:
        catalog = read_catalog(ROOT / "library.json")
        row = next(
            r
            for r in catalog["resources"] + catalog.get("virtual_books", [])
            if r["id"] == item["id"]
        )
        require_shared_permission(row)
        if item["kind"] == "STAGED_REVIEW":
            state = stage_reviewed_pages(
                row, item["previous"], item["reviews"], ROOT / "ingestion-cache"
            )
        else:
            state = prepare(row, ROOT / "ingestion-cache", whole_book=True)
        for _ in range(10):
            with session() as db:
                result = ingest_parts(db, row, state, row["collection"], get_settings(), limit=100)
            item["result"] = result
            atomic_json(JOURNAL, plan)
            if result["status"] == "INDEXED":
                break
        else:
            raise ValueError("FINITE_REVIEW_ACTIVATION_INCOMPLETE")
        item["preparation_path"] = str(
            preparation_folder(ROOT / "ingestion-cache", row) / "preparation.json"
        )
        print(item["id"], result["status"], flush=True)
    # Quality exclusions alter retrieval eligibility, not stored baseline rows.
    env_path = Path(__file__).resolve().parents[1] / ".env"
    content = env_path.read_text(encoding="utf-8-sig").splitlines()
    key = "KNOWLEDGE_QUALITY_EXCLUDED_CHUNK_IDS="
    previous = [line for line in content if line.startswith(key)]
    existing = json.loads(previous[0][len(key) :]) if previous else []
    identifiers = sorted(set(existing + plan["shared_excluded_chunk_ids"]))
    content = [line for line in content if not line.startswith(key)]
    env_path.write_text(
        "\n".join(content + [key + json.dumps(identifiers)]) + "\n", encoding="utf-8"
    )
    atomic_json(JOURNAL, plan)
    print(
        "All reviewed sources indexed; restart Knowledge API to apply two source-quality exclusions.",
        flush=True,
    )


if __name__ == "__main__":
    main()
