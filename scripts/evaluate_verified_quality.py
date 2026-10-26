"""Read-only local retrieval: reviewed pooled relevance and separate citation integrity.

No generation, threshold-based abstention claim or automatic gold annotation.
--broad additionally checks all 100 historical queries; these are not held out
from prior tuning and receive no relevance score without reviewed labels.
"""

import argparse
import hashlib
import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import get_settings
from app.db.models import Chunk, Collection, Document, LibraryBook
from app.db.session import session
from app.library.catalog import atomic_json
from app.library.quality import reviewed_metrics, validate_citations
from scripts.evaluate_retrieval_quality import execute_signed_request

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")
HISTORICAL = ROOT / "reports/quality-review/2026-10-26"
OUTPUT = HISTORICAL / "corrected"


def check_gold(db, questions, owner):
    for q in questions:
        for identifier, label in q["reviewed_qrels"].items():
            chunk = db.get(Chunk, identifier)
            document = db.get(Document, label["document_id"])
            book = db.get(LibraryBook, document.book_id) if document and document.book_id else None
            collection = db.get(Collection, document.collection_id) if document else None
            if not (
                chunk
                and document
                and book
                and collection
                and collection.slug in q["expected_collections"]
                and book.approved
                and document.approved
                and document.status != "DELETED"
                and book.status in {"INDEXED", "PARTIALLY_INDEXED"}
                and book.collection_id == document.collection_id == chunk.collection_id
                and book.visibility == collection.visibility
                and (
                    book.visibility == "CURATED_SHARED"
                    or (book.visibility == "PRIVATE" and str(book.owner_id) == owner)
                )
                and chunk.document_id == document.id
                and chunk.revision == document.active_revision == label["revision"]
                and book.active_generation == document.book_generation
                and book.source_sha256 == label["source_sha256"]
                and hashlib.sha256(chunk.text.encode()).hexdigest() == label["text_sha256"]
                and chunk.page_start == label["physical_page"]
            ):
                raise ValueError("REVIEWED_GOLD_CHANGED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broad", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    owner = json.loads((ROOT / "private-use-approval.json").read_text(encoding="utf-8"))["owner_id"]
    gold_path = OUTPUT / "REVIEWED_PASSAGE_POOL.json"
    questions = json.loads(gold_path.read_text(encoding="utf-8"))["questions"]
    if args.broad:
        broad = json.loads((HISTORICAL / "BENCHMARK_100_DATASET.json").read_text(encoding="utf-8"))
        questions += [
            {
                "id": q["id"],
                "query": q["query"],
                "expected_collections": q["expected_collections"],
                "review_status": "UNJUDGED",
                "unanswerable_label_from_legacy": q["unanswerable"],
            }
            for q in broad["queries"]
        ]
    results = []
    with session() as db, httpx.Client(follow_redirects=False, trust_env=False) as client:
        check_gold(db, [q for q in questions if q.get("review_status") == "REVIEWED"], owner)
        for question in questions:
            for mode in ["keyword", "semantic", "hybrid"]:
                started = time.monotonic()
                try:
                    response = execute_signed_request(
                        client,
                        {
                            "query": question["query"],
                            "collection_ids": question["expected_collections"],
                            "mode": mode,
                            "top_k": 10,
                        },
                        settings.private_scope_secret.get_secret_value(),
                        settings.service_token.get_secret_value(),
                        owner,
                        timeout=15,
                    )
                    response.raise_for_status()
                    data = response.json()
                    hits = data["results"]
                    checks = validate_citations(
                        db,
                        hits,
                        subject=owner,
                        collections=question["expected_collections"],
                        excluded=settings.quality_excluded_chunk_ids,
                    )
                    metrics = (
                        reviewed_metrics(hits, question, checks)
                        if question.get("review_status") == "REVIEWED"
                        else None
                    )
                    results.append(
                        {
                            "question_id": question["id"],
                            "mode": mode,
                            "status": "PASS" if all(checks) else "INVALID_CITATION",
                            "seconds": round(time.monotonic() - started, 4),
                            "fallback": data.get("fallback_reason"),
                            "mode_used": data["retrieval_mode_used"],
                            "citations_checked": len(checks),
                            "invalid_citations": checks.count(False),
                            "metrics": metrics,
                            "hits": [
                                {k: v for k, v in hit.items() if k not in {"text", "snippet"}}
                                for hit in hits
                            ],
                        }
                    )
                except (httpx.HTTPError, ValueError):
                    results.append(
                        {
                            "question_id": question["id"],
                            "mode": mode,
                            "status": "UNAVAILABLE_OR_INVALID",
                            "metrics": None,
                        }
                    )
                # Finite progress; no prompts, source text, credentials or vectors.
                print(question["id"], mode, results[-1]["status"], flush=True)
        probe = next(q for q in questions if q["expected_collections"] == ["personal-library"])
        other = execute_signed_request(
            client,
            {
                "query": probe["query"],
                "collection_ids": ["personal-library"],
                "mode": "keyword",
                "top_k": 5,
            },
            settings.private_scope_secret.get_secret_value(),
            settings.service_token.get_secret_value(),
            str(uuid.uuid4()),
        )
        other.raise_for_status()
        if other.json()["results"]:
            raise ValueError("OWNER_ISOLATION_FAILED")
    summary = {}
    for mode in ["keyword", "semantic", "hybrid"]:
        rows = [r for r in results if r["mode"] == mode]
        judged = [r["metrics"] for r in rows if r.get("metrics")]
        summary[mode] = {
            "requests": len(rows),
            "responses": sum(r["status"] == "PASS" for r in rows),
            "invalid_citations": sum(r.get("invalid_citations", 0) for r in rows),
            "reviewed_queries_scored": len(judged),
            "reviewed_passage_hit_at_5": statistics.mean(m["passage_hit_at_5"] for m in judged)
            if judged
            else None,
            "median_seconds": statistics.median(r["seconds"] for r in rows if "seconds" in r)
            if any("seconds" in r for r in rows)
            else None,
        }
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "Reviewed pooled regression, not a held-out library-wide accuracy estimate. Broad questions test citation integrity only. No new generated-abstention test.",
        "gold_file_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
        "summary": summary,
        "owner_isolation": "PASS",
        "results": results,
    }
    atomic_json(OUTPUT / "VERIFIED_RETRIEVAL_RESULTS.json", payload)
    print(json.dumps(summary), flush=True)
    if any(r["status"] != "PASS" or r.get("fallback") for r in results):
        raise SystemExit("RETRIEVAL_CHECK_FAILED_SEE_PRIVATE_REPORT")


if __name__ == "__main__":
    main()
