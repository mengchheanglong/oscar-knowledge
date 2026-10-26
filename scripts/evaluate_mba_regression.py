"""Repeat the existing 22 MBA questions against the expanded local index.

Baseline document retention measures retrieval stability, not relevance/accuracy.
The original source-family benchmark is preserved and is never re-scored here.
No generation, downloads, document changes or vector exports are performed.
"""

import json
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db.models import Chunk, Collection, Document
from app.db.session import session
from app.library.catalog import atomic_json

BASELINE = Path("D:/AI/OSCAR/mba-corpus/2026-10-25/shared-import/retrieval-evaluation.json")
OUTPUT = Path("D:/AI/OSCAR/Knowledge/Catalog/reports/mba-retrieval-regression.json")


def main():
    settings = get_settings()
    target = make_url(settings.database_url)
    if (
        target.host not in {"127.0.0.1", "localhost"}
        or target.port != 43114
        or target.database != "knowledge"
    ):
        raise ValueError("LOCAL_KNOWLEDGE_DATABASE_REQUIRED")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    if len(baseline["results"]) != 22:
        raise ValueError("EXPECTED_ORIGINAL_22_MBA_QUERIES")
    results = []
    with httpx.Client(timeout=45, trust_env=False) as client, session() as db:
        for original in baseline["results"]:
            started = time.monotonic()
            response = client.post(
                "http://127.0.0.1:8010/internal/v1/retrieve",
                headers={"Authorization": "Bearer " + settings.service_token.get_secret_value()},
                json={
                    "query": original["query"],
                    "collection_ids": ["mba-majors"],
                    "mode": "hybrid",
                    "top_k": 6,
                },
            )
            response.raise_for_status()
            data = response.json()
            rows = data["results"]
            valid = bool(rows)
            for row in rows:
                chunk = db.get(Chunk, uuid.UUID(row["chunk_id"]))
                document = db.get(Document, uuid.UUID(row["document_id"]))
                collection = db.get(Collection, document.collection_id) if document else None
                valid &= bool(
                    chunk
                    and document
                    and document.approved
                    and collection
                    and collection.slug == row["collection_id"] == "mba-majors"
                    and chunk.document_id == document.id
                    and chunk.revision == document.active_revision == row["revision"]
                )
            previous_top = original["results"][0]["document_id"] if original["results"] else None
            result = {
                "major_id": original["major_id"],
                "query": original["query"],
                "mode": data["retrieval_mode_used"],
                "fallback_reason": data.get("fallback_reason"),
                "seconds": round(time.monotonic() - started, 3),
                "active_approved_scope_valid": bool(valid),
                "baseline_top_document_in_top6": any(
                    r["document_id"] == previous_top for r in rows
                ),
                "results": [
                    {
                        k: r.get(k)
                        for k in [
                            "chunk_id",
                            "document_id",
                            "title",
                            "course_code",
                            "source_url",
                            "locator",
                        ]
                    }
                    for r in rows
                ],
            }
            results.append(result)
            print(original["major_id"], "PASS" if valid else "FAIL", result["mode"], flush=True)
    report = {
        "queries": len(results),
        "all_active_approved_scopes_valid": all(r["active_approved_scope_valid"] for r in results),
        "all_hybrid_without_fallback": all(
            r["mode"] == "hybrid" and not r["fallback_reason"] for r in results
        ),
        "baseline_top_document_in_top6": sum(r["baseline_top_document_in_top6"] for r in results),
        "scope": "Scope/integrity and baseline document stability; not a new source-family accuracy score.",
        "results": results,
    }
    atomic_json(OUTPUT, report)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))
    if not report["all_active_approved_scopes_valid"] or not report["all_hybrid_without_fallback"]:
        raise ValueError("MBA_RETRIEVAL_REGRESSION_FAILED")


if __name__ == "__main__":
    main()
