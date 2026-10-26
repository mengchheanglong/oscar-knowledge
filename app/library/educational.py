"""Fail-closed receipts for bounded human/assistant educational source reviews.

This validates evidence bindings, not the correctness of an educational judgment.
Private review text and source material are deliberately external to Git.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

REVIEWED = "REVIEWED_FOR_SELF_STUDY_CONCEPT_COVERAGE_WITH_LIMITATIONS"


def input_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def verified_review(
    record: dict[str, Any] | None,
    expected_input: Any,
    hashes: dict[str, str] | None = None,
) -> bool:
    """Missing, revoked, incomplete or stale review evidence never promotes a row.

    ``hashes`` is a per-audit cache; callers must not reuse it across audit runs.
    """
    if (
        not record
        or record.get("status") != REVIEWED
        or record.get("input_sha256") != input_digest(expected_input)
        or not record.get("rationale", "").strip()
        or not record.get("limits", "").strip()
        or not record.get("files")
    ):
        return False
    hashes = hashes if hashes is not None else {}
    try:
        for proof in record["files"]:
            path = Path(proof["path"])
            key = str(path.resolve())
            if key not in hashes:
                digest = hashlib.sha256()
                with path.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                hashes[key] = digest.hexdigest()
            if hashes[key] != proof["sha256"]:
                return False
    except (OSError, KeyError, TypeError):
        return False
    return True
