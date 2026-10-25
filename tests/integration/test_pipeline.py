from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.schemas import Filters, RetrievalRequest
from app.config import Settings
from app.db.models import Chunk, ChunkEmbedding, Document, IngestionJob
from app.embeddings.provider import OpenAICompatible
from app.ingestion.pipeline import enqueue, process_job
from app.retrieval.hybrid import retrieve

pytestmark = pytest.mark.integration


def test_unchanged_import_does_not_resurrect_concurrently_deleted_document(
    db, tmp_path, monkeypatch
):
    from sqlalchemy.orm import Session

    path = tmp_path / "note.md"
    path.write_text("# Pricing\n\nAn original pricing note.")
    first = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, first.id, Settings()) == "INDEXED"
    second = enqueue(db, path, "mba-business", approved=True)

    class ConcurrentDelete:
        batch_results = []

        @property
        def identity(self):
            with Session(db.get_bind()) as other:
                doc = other.get(Document, first.document_id)
                doc.status = "DELETED"
                other.commit()
            return None

    monkeypatch.setattr("app.ingestion.pipeline.provider", lambda settings: ConcurrentDelete())
    assert process_job(db, second.id, Settings()) == "FAILED"
    assert db.get(Document, first.document_id).status == "DELETED"
    assert db.get(Document, first.document_id).active_revision == 1


def test_atomic_revisions_idempotency_failure_and_restart(db, tmp_path):
    path = tmp_path / "lecture.md"
    path.write_text("# Pricing\n\nSubscription pricing uses willingness to pay.", encoding="utf-8")
    job = enqueue(db, path, "mba-business", approved=True, course_code="DEMO", subject="Marketing")
    assert process_job(db, job.id, Settings()) == "INDEXED"
    doc = db.get(Document, job.document_id)
    first_ids = list(db.scalars(select(Chunk.id)))
    assert doc.active_revision == 1
    natural = retrieve(
        db,
        RetrievalRequest(
            query="How should Rentify test its subscription pricing, using the synthetic course notes?"
        ),
        Settings(),
    )
    assert natural.results and natural.results[0].document_id == doc.id
    job2 = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job2.id, Settings()) == "UNCHANGED"
    assert list(db.scalars(select(Chunk.id))) == first_ids
    path.write_text("# Pricing\n\nNew subscription pricing improves conversion.")
    job3 = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job3.id, Settings()) == "INDEXED"
    assert doc.active_revision == 2
    path.write_bytes(b"\xff")
    failed = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, failed.id, Settings()) == "FAILED"
    assert doc.active_revision == 2
    result = retrieve(db, RetrievalRequest(query="subscription pricing"), Settings())
    assert result.retrieval_mode_used == "keyword"
    assert len(result.results) == 1 and result.results[0].revision == 2
    path.write_text("# Pricing\n\nRestarted subscription pricing.")
    assert process_job(db, failed.id, Settings()) == "INDEXED"
    assert db.get(IngestionJob, failed.id).attempts == 2
    stale = enqueue(db, path, "mba-business", approved=True)
    stale.status = "PROCESSING"
    stale.started_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    assert process_job(db, stale.id, Settings()) == "UNCHANGED"


def test_collection_approval_deletion_and_filters(db, tmp_path):
    path = tmp_path / "lecture.md"
    path.write_text("# Pricing\n\nPricing experiments")
    job = enqueue(
        db,
        path,
        "mba-business",
        approved=True,
        course_code="DEMO",
        subject="Marketing",
        publication_year=2026,
    )
    assert process_job(db, job.id, Settings()) == "INDEXED"
    assert not retrieve(
        db, RetrievalRequest(query="pricing", filters=Filters(subject=["Finance"])), Settings()
    ).results
    assert retrieve(
        db,
        RetrievalRequest(
            query="pricing", filters=Filters(course=["DEMO"], publication_year=[2026])
        ),
        Settings(),
    ).results
    with pytest.raises(PermissionError):
        retrieve(db, RetrievalRequest(query="pricing", collection_ids=["private"]), Settings())
    doc = db.get(Document, job.document_id)
    doc.approved = False
    db.commit()
    assert not retrieve(db, RetrievalRequest(query="pricing"), Settings()).results
    doc.approved, doc.status = True, "DELETED"
    db.commit()
    assert not retrieve(db, RetrievalRequest(query="pricing"), Settings()).results


def test_real_pgvector_model_filter_and_hybrid(db, tmp_path, monkeypatch):
    path = tmp_path / "lecture.md"
    path.write_text("# Network\n\nNetwork effects create value for customers.")
    settings = Settings(embedding_provider="openai", embedding_api_key="fake-never-used")
    vector = [1.0] + [0.0] * 1535
    monkeypatch.setattr(OpenAICompatible, "embed", lambda self, texts: [vector for _ in texts])
    job = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job.id, settings) == "INDEXED"
    for mode in ["semantic", "hybrid"]:
        result = retrieve(db, RetrievalRequest(query="network", mode=mode), settings)
        assert result.retrieval_mode_used == mode
        assert len(result.results) == 1
    chunk = db.scalar(select(ChunkEmbedding))
    chunk.identity = "incompatible-model"
    db.commit()
    assert not retrieve(db, RetrievalRequest(query="network", mode="semantic"), settings).results


def test_quota_and_busy_job(db, tmp_path):
    path = tmp_path / "lecture.md"
    path.write_text("Pricing text")
    job = enqueue(db, path, "mba-business", approved=True)
    job.status, job.started_at = "PROCESSING", datetime.now(UTC)
    db.commit()
    assert process_job(db, job.id, Settings()) == "BUSY"
    job.status = "QUEUED"
    db.commit()
    assert process_job(db, job.id, Settings(max_storage_chars=1)) == "FAILED"
    assert db.get(Document, job.document_id).active_revision == 0


def test_deleted_document_is_not_resurrected_by_queued_job(db, tmp_path):
    path = tmp_path / "lecture.md"
    path.write_text("Pricing text")
    job = enqueue(db, path, "mba-business", approved=True)
    assert process_job(db, job.id, Settings()) == "INDEXED"
    queued = enqueue(db, path, "mba-business", approved=True)
    doc = db.get(Document, job.document_id)
    doc.status = "DELETED"
    db.commit()
    assert process_job(db, queued.id, Settings()) == "FAILED"
    assert doc.status == "DELETED"
    assert not retrieve(db, RetrievalRequest(query="pricing"), Settings()).results
