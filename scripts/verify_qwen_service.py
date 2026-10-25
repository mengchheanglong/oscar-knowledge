"""Explicit live acceptance: imports an original CC0 note and preserves existing data."""

import argparse
import json
import time
from pathlib import Path

import httpx
from sqlalchemy import select

from app.api.schemas import RetrievalRequest
from app.config import get_settings
from app.db.models import Chunk, Document
from app.db.session import session
from app.ingestion.pipeline import enqueue, process_job
from app.ingestion.reembedding import enqueue_reembed
from app.retrieval.hybrid import retrieve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    settings = get_settings()
    assert settings.embedding_provider == "ollama"
    path = Path("data/qwen-acceptance.md").resolve()
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "# Warehouse replenishment\n\n"
        "Original CC0 verification note, authored for this local acceptance check. "
        "The reorder point equals expected demand during supplier lead time plus safety stock. "
        "For daily demand of 12 cartons, lead time of 5 days and safety stock of 15 cartons, "
        "reorder when inventory reaches 75 cartons.\n",
        encoding="utf-8",
    )
    report = {"generation": "none; retrieval only", "corpus": "original synthetic CC0 notes"}
    with session() as db:
        start = time.perf_counter()
        job = enqueue(
            db,
            path,
            "mba-business",
            approved=True,
            canonical_key="local-qwen-acceptance",
            title="Local Qwen warehouse verification",
            course_code="LOCAL-QWEN-TEST",
            license_type="CC0-1.0",
        )
        outcome = process_job(db, job.id, settings)
        assert outcome in {"INDEXED", "UNCHANGED"}, outcome
        report["ingestion"] = {"outcome": outcome, "seconds": time.perf_counter() - start}
        docs = list(db.scalars(select(Document).where(Document.approved.is_(True))))
        before = [(str(d.id), d.active_revision, d.content_sha256) for d in docs]
        chunks_before = list(db.execute(select(Chunk.id, Chunk.revision, Chunk.embedding_identity)))
        questions = json.loads(Path("fixtures/eval_questions.json").read_text())["questions"]

        def evaluate(config, mode):
            reciprocal, recalls, hits, latencies, fallbacks = [], [], [], [], []
            for item in questions:
                gold = set(
                    db.scalars(
                        select(Document.id).where(Document.canonical_key.in_(item["source_keys"]))
                    )
                )
                assert len(gold) == len(item["source_keys"])
                start = time.perf_counter()
                result = retrieve(db, RetrievalRequest(query=item["query"], mode=mode), config)
                latencies.append(time.perf_counter() - start)
                if result.fallback_reason:
                    fallbacks.append(result.fallback_reason)
                found = [r.document_id for r in result.results]
                hits.append(int(bool(set(found) & gold)))
                recalls.append(len(set(found) & gold) / len(gold))
                reciprocal.append(
                    next((1 / rank for rank, doc_id in enumerate(found, 1) if doc_id in gold), 0)
                )
            return {
                "questions": len(hits),
                "Hit@6": sum(hits) / len(hits),
                "Recall@6": sum(recalls) / len(recalls),
                "MRR@6": sum(reciprocal) / len(reciprocal),
                "mean_seconds": sum(latencies) / len(latencies),
                "max_seconds": max(latencies),
                "fallbacks": fallbacks,
            }

        report["fixture_evaluation"] = {
            mode: evaluate(settings, mode) for mode in ["keyword", "semantic", "hybrid"]
        }
        raw = settings.model_copy(update={"ollama_query_instruction": ""})
        start = time.perf_counter()
        for doc in docs:
            job = enqueue_reembed(db, doc.id, raw)
            assert process_job(db, job.id, raw) in {"EMBEDDED", "UNCHANGED"}
        report["alternate_instruction_reembedding_seconds"] = time.perf_counter() - start
        report["fixture_evaluation"]["semantic_without_instruction"] = evaluate(raw, "semantic")
        for doc in docs:
            job = enqueue_reembed(db, doc.id, settings)
            assert process_job(db, job.id, settings) == "UNCHANGED"
        db.expire_all()
        after = [
            (str(d.id), d.active_revision, d.content_sha256)
            for d in db.scalars(select(Document).where(Document.approved.is_(True)))
        ]
        assert sorted(before) == sorted(after)
        assert chunks_before == list(
            db.execute(select(Chunk.id, Chunk.revision, Chunk.embedding_identity))
        )
        report["reembedding_preserved_document_ids_revisions_hashes_and_legacy_columns"] = True
        offline = settings.model_copy(update={"ollama_base_url": "http://127.0.0.1:9"})
        fallback = retrieve(db, RetrievalRequest(query="reorder point", mode="hybrid"), offline)
        assert fallback.retrieval_mode_used == "keyword" and fallback.fallback_reason
        report["offline_check"] = {
            "method": "real refused connection to local port 9",
            "mode": fallback.retrieval_mode_used,
            "reason": fallback.fallback_reason,
        }

    report["http_retrieval"] = {}
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=10, trust_env=False) as client:
        for mode in ["semantic", "hybrid"]:
            start = time.perf_counter()
            response = client.post(
                "/internal/v1/retrieve",
                headers={"Authorization": "Bearer " + settings.service_token.get_secret_value()},
                json={
                    "query": "When should we replenish cartons if supplier lead time is five days?",
                    "mode": mode,
                },
            )
            response.raise_for_status()
            data = response.json()
            assert data["retrieval_mode_used"] == mode and data["fallback_reason"] is None
            assert data["results"][0]["course_code"] == "LOCAL-QWEN-TEST"
            assert data["results"][0]["locator"] == "Warehouse replenishment"
            report["http_retrieval"][mode] = {
                "seconds": time.perf_counter() - start,
                "result": data["results"][0],
            }
    Path("docs/QWEN_SERVICE_VERIFICATION.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
