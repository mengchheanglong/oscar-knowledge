"""Stage source-bound reviewed excerpts without rerunning OCR or replacing originals."""

import copy
import hashlib
import json
from pathlib import Path

from app.config import Settings
from app.ingestion.chunking import chunk_segments
from app.ingestion.loaders import load
from app.library.books import preparation_folder, require_shared_permission
from app.library.catalog import atomic_json, digest
from app.library.source import verify_source


def stage_reviewed_pages(resource, previous, reviews, cache: Path):
    require_shared_permission(resource)
    if resource["access"]["visibility"] != "PRIVATE":
        raise ValueError("PRIVATE_REVIEW_REQUIRED")
    verify_source(resource)
    if not previous.get("complete") or previous["source_sha256"] != resource["sha256"]:
        raise ValueError("COMPLETE_SOURCE_PREPARATION_REQUIRED")
    if not reviews or any(
        r.get("source_sha256") != resource["sha256"]
        or r.get("resource_id") != resource["id"]
        or not r.get("review_method")
        or not r.get("image_sha256")
        or not 20 <= len(r.get("text", "")) <= 100000
        for r in reviews
    ):
        raise ValueError("SOURCE_BOUND_PAGE_REVIEW_REQUIRED")
    by_page = {r["physical_page"]: r for r in reviews}
    if len(by_page) != len(reviews):
        raise ValueError("DUPLICATE_PAGE_REVIEW")
    signature = hashlib.sha256(json.dumps(reviews, sort_keys=True).encode()).hexdigest()
    folder = preparation_folder(cache, resource)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "preparation.json"
    if target.exists():
        result = json.loads(target.read_text(encoding="utf-8"))
        if result.get("review_manifest_sha256") != signature:
            raise ValueError("REVIEW_REVISION_CONFLICT")
        return result
    result = copy.deepcopy(previous)
    result["parts"] = []
    found = set()
    for part in previous["parts"]:
        original = Path(part["path"])
        path = folder / original.name
        if path.resolve() == original.resolve():
            raise ValueError("NEW_REVIEW_REVISION_REQUIRED")
        if digest(original) != part["sha256"]:
            raise ValueError("PREPARED_PART_CHANGED")
        data = json.loads(original.read_text(encoding="utf-8"))
        data["metadata"]["source_notice"] = resource.get("source_notice")
        for page in data["pages"]:
            review = by_page.get(page["page"])
            if not review:
                continue
            found.add(page["page"])
            page["text"] = review["text"]
            page.setdefault("metadata", {}).update(
                extraction="VISUAL_DESCRIPTION",
                reviewed_excerpt=True,
                review_manifest_sha256=signature,
            )
        atomic_json(path, data)
        expected = len(
            list(
                chunk_segments(
                    load(path, Settings(embedding_provider="disabled", embedding_dimensions=1536))
                )
            )
        )
        result["parts"].append(
            {**part, "path": str(path), "sha256": digest(path), "expected_chunks": expected}
        )
    if found != set(by_page):
        raise ValueError("REVIEW_PAGE_NOT_IN_PREPARATION")
    result["ocr_pages"] = [p for p in result.get("ocr_pages", []) if p not in found]
    result["reviewed_excerpt_pages"] = sorted(set(result.get("reviewed_excerpt_pages", [])) | found)
    result["review_manifest_sha256"] = signature
    atomic_json(target, result)
    return result
