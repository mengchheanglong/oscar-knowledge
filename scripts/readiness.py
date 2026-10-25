"""Read-only local readiness; no credentials, private text, downloads or paid calls."""

import argparse
import json
from pathlib import Path

import httpx
from sqlalchemy import func, select, text

from app.config import get_settings
from app.db.models import Chunk, ChunkEmbedding, Collection, Document
from app.db.session import session
from app.embeddings.provider import provider


def check(collection):
    settings = get_settings()
    report = {
        "Ollama": "UNAVAILABLE",
        "Embedding model": "MISSING",
        "Knowledge database": "UNAVAILABLE",
        "Knowledge API": "UNAVAILABLE",
        "OSCAR Backend": "UNAVAILABLE",
        "OSCAR Frontend": "UNAVAILABLE",
        "Knowledge collection": collection,
        "Document count": None,
        "Compatible embedded chunks": None,
        "Retrieval mode": "UNAVAILABLE",
    }
    embedder = provider(settings)
    identity = embedder.identity if embedder and settings.embedding_model_revision else None
    with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
        try:
            client.get(settings.ollama_base_url + "/api/version").raise_for_status()
            report["Ollama"] = "READY"
            models = client.get(settings.ollama_base_url + "/api/tags").json()["models"]
            if any(
                m.get("name") == settings.embedding_model
                and (
                    not settings.embedding_model_revision
                    or m.get("digest") == settings.embedding_model_revision.removeprefix("sha256:")
                )
                for m in models
            ):
                report["Embedding model"] = "AVAILABLE"
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
        for key, url in [
            ("Knowledge API", "http://127.0.0.1:8010/health/ready"),
            ("OSCAR Backend", "http://127.0.0.1:43101/api/v1/health/ready"),
            ("OSCAR Frontend", "http://127.0.0.1:43100/assistant"),
        ]:
            try:
                if client.get(url).status_code == 200:
                    report[key] = "READY"
            except httpx.HTTPError:
                pass
        try:
            response = client.post(
                "http://127.0.0.1:8010/internal/v1/retrieve",
                headers={"Authorization": "Bearer " + settings.service_token.get_secret_value()},
                json={
                    "query": "customer segmentation and market opportunity",
                    "collection_ids": [collection],
                    "mode": "hybrid",
                    "top_k": 1,
                },
            )
            response.raise_for_status()
            result = response.json()
            report["Retrieval mode"] = result["retrieval_mode_used"].upper()
            report["Retrieval fallback"] = result.get("fallback_reason")
            report["Retrieval result count"] = len(result["results"])
        except (httpx.HTTPError, ValueError, KeyError):
            pass
    try:
        with session() as db:
            if db.scalar(text("SELECT version_num FROM alembic_version")) != "0002":
                raise ValueError("MIGRATION_REQUIRED")
            if collection not in settings.allowed_collections:
                raise ValueError("COLLECTION_NOT_ALLOWED")
            approved = [
                Collection.slug == collection,
                Document.approved.is_(True),
                Document.status != "DELETED",
                Document.active_revision > 0,
            ]
            report["Document count"] = db.scalar(
                select(func.count()).select_from(Document).join(Collection).where(*approved)
            )
            report["Compatible embedded chunks"] = db.scalar(
                select(func.count())
                .select_from(ChunkEmbedding)
                .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
                .join(Document, Document.id == Chunk.document_id)
                .join(Collection, Collection.id == Document.collection_id)
                .where(
                    *approved,
                    Chunk.revision == Document.active_revision,
                    ChunkEmbedding.identity == identity,
                    ChunkEmbedding.dimensions == settings.embedding_dimensions,
                )
            )
            report["Knowledge database"] = "READY"
    except Exception:
        pass
    report["ready"] = (
        all(
            report[key] == "READY"
            for key in [
                "Ollama",
                "Knowledge database",
                "Knowledge API",
                "OSCAR Backend",
                "OSCAR Frontend",
            ]
        )
        and report["Embedding model"] == "AVAILABLE"
        and report["Retrieval mode"] == "HYBRID"
        and bool(report["Compatible embedded chunks"])
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="mba-mit-demo")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = check(args.collection)
    except Exception:
        # Settings validation can include raw environment input in its exception.
        # Never print that diagnostic or a database/provider exception here.
        report = {
            "ready": False,
            "Configuration": "UNAVAILABLE; check local configuration privately",
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
