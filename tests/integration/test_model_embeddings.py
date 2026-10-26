import os

import httpx
import pytest
from sqlalchemy import select, func

from app.api.schemas import RetrievalRequest
from app.config import Settings
from app.db.models import Chunk, ChunkEmbedding, Document, IngestionJob
from app.embeddings.ollama_provider import OllamaEmbedding
from app.embeddings.base import EmbeddingError
from app.ingestion.pipeline import enqueue, process_job
from app.ingestion.reembedding import enqueue_reembed
from app.retrieval.hybrid import retrieve

pytestmark = pytest.mark.integration
DIGEST = "a" * 64


def local_settings(**extra):
    return Settings(
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=1024,
        embedding_model_revision=DIGEST,
        **extra,
    )


def test_reembed_preserves_ids_revisions_legacy_vectors_and_failed_model(db, tmp_path, monkeypatch):
    path = tmp_path / "pricing.md"
    path.write_text(
        "# Pricing\n\nSubscription pricing experiments compare basic and premium plans."
    )
    initial = enqueue(
        db,
        path,
        "mba-business",
        approved=True,
        course_code="TEST",
        source_url="https://example.org/pricing",
    )
    assert process_job(db, initial.id, Settings()) == "INDEXED"
    chunk = db.scalar(select(Chunk))
    ids = (chunk.id, chunk.document_id, chunk.revision)
    chunk.embedding, chunk.embedding_identity = (
        [1.0] + [0.0] * 1535,
        "https://api.openai.com/v1|text-embedding-3-small|1536",
    )
    db.commit()
    path.unlink()  # Re-embedding must use stored text, not a download or re-upload.
    monkeypatch.setattr(
        OllamaEmbedding, "embed", lambda self, texts: [[1.0] + [0.0] * 1023 for _ in texts]
    )
    monkeypatch.setattr(OllamaEmbedding, "embed_query", lambda self, text: [1.0] + [0.0] * 1023)
    settings = local_settings()
    job = enqueue_reembed(db, chunk.document_id, settings)
    assert process_job(db, job.id, settings) == "EMBEDDED"
    assert (chunk.id, chunk.document_id, chunk.revision) == ids
    assert len(chunk.embedding) == 1536
    assert db.scalar(select(func.count()).select_from(ChunkEmbedding)) == 1
    result = retrieve(
        db, RetrievalRequest(query="tiered membership costs", mode="semantic"), settings
    )
    assert result.results[0].chunk_id == chunk.id and result.results[0].locator == "Pricing"
    assert result.results[0].source_url == "https://example.org/pricing"
    again = enqueue_reembed(db, chunk.document_id, settings)
    assert process_job(db, again.id, settings) == "UNCHANGED"
    changed = local_settings(ollama_query_instruction="Different instruction")
    assert not retrieve(db, RetrievalRequest(query="pricing", mode="semantic"), changed).results
    monkeypatch.setattr(
        OllamaEmbedding,
        "embed",
        lambda *a: (_ for _ in ()).throw(EmbeddingError("EMBEDDING_UNAVAILABLE")),
    )
    failed = enqueue_reembed(db, chunk.document_id, changed)
    assert process_job(db, failed.id, changed) == "FAILED"
    assert db.get(Document, chunk.document_id).active_revision == 1
    assert db.scalar(select(func.count()).select_from(ChunkEmbedding)) == 1
    assert db.get(IngestionJob, failed.id).error_code == "EMBEDDING_UNAVAILABLE"
    assert retrieve(db, RetrievalRequest(query="pricing", mode="semantic"), settings).results
    openai = Settings(embedding_provider="openai", embedding_api_key="test-only")
    from app.embeddings.openai_provider import OpenAICompatible

    monkeypatch.setattr(OpenAICompatible, "embed_query", lambda *a: [1.0] + [0.0] * 1535)
    assert (
        retrieve(db, RetrievalRequest(query="pricing", mode="semantic"), openai).results[0].chunk_id
        == chunk.id
    )


def test_offline_keyword_hybrid_and_explicit_semantic(db, tmp_path, monkeypatch):
    path = tmp_path / "source.md"
    path.write_text("# Pricing\n\nSubscription pricing")
    job = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job.id, Settings()) == "INDEXED"
    monkeypatch.setattr(
        OllamaEmbedding,
        "embed_query",
        lambda *a: (_ for _ in ()).throw(EmbeddingError("EMBEDDING_UNAVAILABLE")),
    )
    settings = local_settings()
    keyword = retrieve(db, RetrievalRequest(query="pricing", mode="keyword"), settings)
    assert keyword.results and keyword.retrieval_mode_used == "keyword"
    hybrid = retrieve(db, RetrievalRequest(query="pricing", mode="hybrid"), settings)
    assert hybrid.results and hybrid.fallback_reason == "EMBEDDING_UNAVAILABLE"
    assert hybrid.retrieval_mode_used == "keyword"
    with pytest.raises(EmbeddingError):
        retrieve(db, RetrievalRequest(query="pricing", mode="semantic"), settings)
    with pytest.raises(EmbeddingError):
        retrieve(db, RetrievalRequest(query="pricing", mode="semantic"), Settings())


def test_identical_copies_do_not_crowd_distinct_evidence_or_change_stored_sources(
    db, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        OllamaEmbedding, "embed", lambda self, texts: [[1.0] + [0.0] * 1023 for _ in texts]
    )
    monkeypatch.setattr(OllamaEmbedding, "embed_query", lambda self, text: [1.0] + [0.0] * 1023)
    settings = local_settings()
    repeated = "Feedback loops adjust outcomes in a system."
    distinct = (
        "Feedback loops can amplify changes or stabilize a system with balancing adjustments."
    )
    for number, content in enumerate([repeated, repeated, repeated, distinct]):
        path = tmp_path / f"source-{number}.md"
        path.write_text(content)
        job = enqueue(db, path, "mba-business", approved=True)
        assert process_job(db, job.id, settings) == "INDEXED"
    for mode in ["keyword", "semantic", "hybrid"]:
        before = db.scalar(select(func.current_setting("enable_nestloop")))
        response = retrieve(db, RetrievalRequest(query="feedback", mode=mode), settings)
        assert len(response.results) == 2
        assert {r.text for r in response.results} == {repeated, distinct}
        assert db.scalar(select(func.current_setting("enable_nestloop"))) == before
    assert db.scalar(select(func.count()).select_from(Document)) == 4
    assert db.scalar(select(func.count()).select_from(Chunk)) == 4
    assert db.scalar(select(func.count()).select_from(ChunkEmbedding)) == 4


@pytest.mark.skipif(
    os.getenv("KNOWLEDGE_TEST_LOCAL_MODEL") != "1",
    reason="Explicit opt-in required for actual local Ollama inference",
)
def test_real_local_model_ingestion_and_retrieval(db, tmp_path):
    with httpx.Client(trust_env=False) as client:
        digest = next(
            m["digest"]
            for m in client.get("http://127.0.0.1:11434/api/tags").json()["models"]
            if m["name"] == "qwen3-embedding:0.6b"
        )
    settings = Settings(
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=1024,
        embedding_model_revision=digest,
        embedding_query_timeout_seconds=10,
    )
    path = tmp_path / "lecture.md"
    path.write_text(
        "# Subscription pricing\n\nCompare basic and premium membership plans using willingness to pay, conversion and retention."
    )
    job = enqueue(db, path, "mba-business", approved=True, course_code="REAL-LOCAL-TEST")
    assert process_job(db, job.id, settings) == "INDEXED"
    for mode in ["semantic", "hybrid"]:
        result = retrieve(
            db,
            RetrievalRequest(query="How should we test tiered membership fees?", mode=mode),
            settings,
        )
        assert result.retrieval_mode_used == mode
        assert result.results[0].course_code == "REAL-LOCAL-TEST"
        assert result.results[0].locator == "Subscription pricing"
