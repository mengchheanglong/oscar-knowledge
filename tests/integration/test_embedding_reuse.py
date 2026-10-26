import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.models import Chunk, ChunkEmbedding, IngestionJob
from app.ingestion.pipeline import enqueue, process_job

pytestmark = pytest.mark.integration


def test_exact_text_reuses_model_work_but_keeps_independent_provenance(db, tmp_path, monkeypatch):
    class Embedder:
        dimensions = 1024
        identity = "test-local-model-v1"
        legacy_identity = None
        batch_results = []
        calls = 0

        def embed_documents(self, texts):
            self.calls += 1
            return [[1.0] + [0.0] * 1023 for _ in texts]

    embedder = Embedder()
    monkeypatch.setattr("app.ingestion.pipeline.provider", lambda settings: embedder)
    jobs = []
    for name in ["first.md", "second.md"]:
        path = tmp_path / name
        path.write_text(
            "# Original test\n\nExactly identical original fixture input.", encoding="utf-8"
        )
        job = enqueue(db, path, "mba-business", approved=True)
        assert process_job(db, job.id, Settings()) == "INDEXED"
        jobs.append(job)
    assert embedder.calls == 1
    assert jobs[0].document_id != jobs[1].document_id
    chunks = list(db.scalars(select(Chunk)))
    assert len(chunks) == 2 and chunks[0].id != chunks[1].id
    assert len(list(db.scalars(select(ChunkEmbedding)))) == 2
    assert db.get(IngestionJob, jobs[1].id).checkpoint["embedding_batches"] == [
        {"status": "REUSED_EXACT_TEXT", "count": 1}
    ]
    embedder.identity = "test-local-model-v2"
    path = tmp_path / "third.md"
    path.write_text(
        "# Original test\n\nExactly identical original fixture input.", encoding="utf-8"
    )
    job = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job.id, Settings()) == "INDEXED"
    assert embedder.calls == 2
