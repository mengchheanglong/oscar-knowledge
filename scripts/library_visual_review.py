"""Render exact-pixel grouped unresolved PDF pages; apply explicit reviewed outcomes."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pymupdf

from app.library.books import preparation_folder
from app.library.catalog import atomic_json, catalog_lock, read_catalog

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def collect(output):
    catalog = read_catalog(output / "library.json")
    queue_file = output / "reports" / "visual-review.json"
    queue = (
        json.loads(queue_file.read_text(encoding="utf-8"))
        if queue_file.exists()
        else {"groups": {}}
    )
    for row in catalog["resources"] + catalog.get("virtual_books", []):
        if row["format"] != "pdf" or row.get("preparation_version") != 3:
            continue
        state_path = preparation_folder(output / "ingestion-cache", row) / "preparation.json"
        if not state_path.exists():
            continue
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not state.get("complete") or not state["ocr_required_pages"]:
            continue
        with pymupdf.open(row["absolute_path"]) as pdf:
            for number in state["ocr_required_pages"]:
                pix = pdf[number - 1].get_pixmap(
                    matrix=pymupdf.Matrix(0.75, 0.75), colorspace=pymupdf.csRGB, alpha=False
                )
                digest = hashlib.sha256(
                    f"{pix.width}:{pix.height}:".encode() + pix.samples
                ).hexdigest()
                image = output / "reports" / "visual-review" / f"{digest}.png"
                if not image.exists():
                    image.parent.mkdir(exist_ok=True)
                    pix.save(image)
                group = queue["groups"].setdefault(
                    digest,
                    {
                        "image": str(image),
                        "classification": "REVIEW_REQUIRED",
                        "text": None,
                        "instances": [],
                    },
                )
                instance = {"id": row["id"], "page": number, "source_sha256": row["sha256"]}
                if instance not in group["instances"]:
                    group["instances"].append(instance)
    atomic_json(queue_file, queue)
    print(
        "Visual groups",
        len(queue["groups"]),
        "awaiting review",
        sum(r["classification"] == "REVIEW_REQUIRED" for r in queue["groups"].values()),
        flush=True,
    )


def apply(output):
    queue = json.loads((output / "reports" / "visual-review.json").read_text(encoding="utf-8"))
    touched = set()
    with catalog_lock(output):
        catalog = read_catalog(output / "library.json")
        rows = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}
        for group_id, group in queue["groups"].items():
            kind = group["classification"]
            if kind == "REVIEW_REQUIRED":
                continue
            if kind not in {
                "NON_TEXT_DECORATION",
                "VISUAL_DESCRIPTION",
                "VISUALLY_REVIEWED_TRANSCRIPTION",
            } or not group.get("reviewer"):
                raise ValueError("EXPLICIT_VISUAL_REVIEW_REQUIRED")
            text = group.get("text")
            if kind != "NON_TEXT_DECORATION" and (not text or len(text) > 10000):
                raise ValueError("BOUNDED_VISUAL_TRANSCRIPTION_REQUIRED")
            for instance in group["instances"]:
                row = rows[instance["id"]]
                if row["sha256"] != instance["source_sha256"]:
                    raise ValueError("VISUAL_REVIEW_SOURCE_CHANGED")
                previous = row.setdefault("page_reviews", {}).get(str(instance["page"]), {})
                if (
                    previous.get("source_sha256") == row["sha256"]
                    and previous.get("classification") == kind
                    and previous.get("text") == text
                ):
                    continue
                row["page_reviews"][str(instance["page"])] = {
                    "source_sha256": row["sha256"],
                    "classification": kind,
                    "extraction": kind,
                    "text": text,
                    "reviewer": group["reviewer"],
                    "evidence": group["image"],
                    "exact_pixel_group": group_id,
                    "reviewed_on": datetime.now(UTC).isoformat(),
                }
                touched.add(row["id"])
        for identifier in touched:
            row = rows[identifier]
            row["preparation_revision"] = row.get("preparation_revision", 0) + 1
            row["physical_page_buckets"] = True
        atomic_json(output / "library.json", catalog)
    print("Reviewed resources staged for incremental preparation", len(touched))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    apply(args.catalog_dir) if args.apply else collect(args.catalog_dir)
