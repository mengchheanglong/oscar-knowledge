"""Re-embed immutable active chunks; never require a re-download or change chunk IDs."""

from datetime import UTC, datetime

from sqlalchemy import select, func

from app.db.models import Chunk, ChunkEmbedding, Collection, Document, IngestionJob
from app.embeddings.base import EmbeddingError
from app.embeddings.provider import provider
from app.embeddings.storage import store_vectors


def enqueue_reembed(db, document_id, settings):
    doc = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if not doc or not doc.approved or doc.status == "DELETED" or doc.active_revision == 0:
        raise EmbeddingError("DOCUMENT_NOT_AVAILABLE")
    col = db.get(Collection, doc.collection_id)
    if not col or col.slug not in settings.allowed_collections:
        raise EmbeddingError("COLLECTION_NOT_ALLOWED")
    job = db.scalar(
        select(IngestionJob).where(
            IngestionJob.document_id == doc.id, IngestionJob.status.in_(["QUEUED", "PROCESSING"])
        )
    )
    if job:
        db.commit()
        return job
    count = (
        db.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.status.in_(["QUEUED", "PROCESSING"]))
        )
        or 0
    )
    if count >= settings.max_pending_jobs:
        raise EmbeddingError("QUEUE_LIMIT")
    job = IngestionJob(document_id=doc.id, checkpoint={"operation": "reembed"})
    db.add(job)
    db.commit()
    return job


def perform_reembedding(db, job, settings):
    job_id, document_id = job.id, job.document_id
    lease = job.checkpoint["lease_token"]
    embedder = None
    try:
        doc = db.get(Document, document_id)
        if not doc or not doc.approved or doc.status == "DELETED":
            raise EmbeddingError("DOCUMENT_NOT_AVAILABLE")
        revision = doc.active_revision
        chunks = list(
            db.scalars(
                select(Chunk)
                .where(Chunk.document_id == doc.id, Chunk.revision == revision)
                .order_by(Chunk.ordinal)
                .limit(settings.embedding_max_document_chunks + 1)
            )
        )
        if not chunks or len(chunks) > settings.embedding_max_document_chunks:
            raise EmbeddingError("EMBEDDING_DOCUMENT_BUDGET")
        db.commit()  # No document/DB locks during local inference.
        embedder = provider(settings)
        if not embedder:
            raise EmbeddingError("EMBEDDING_DISABLED")
        identity = embedder.identity
        existing = set(
            db.scalars(
                select(ChunkEmbedding.chunk_id).where(
                    ChunkEmbedding.identity == identity,
                    ChunkEmbedding.chunk_id.in_([c.id for c in chunks]),
                )
            )
        )
        missing = [chunk for chunk in chunks if chunk.id not in existing]
        job.stage, job.progress = "embed", 30
        job.checkpoint = {**job.checkpoint, "target_identity": identity, "revision": revision}
        db.commit()
        vectors = embedder.embed_documents([c.text for c in missing]) if missing else []
        doc = db.scalar(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current_job = db.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not current_job or current_job.checkpoint.get("lease_token") != lease:
            raise EmbeddingError("JOB_LEASE_LOST")
        job = current_job
        if (
            not doc
            or not doc.approved
            or doc.status == "DELETED"
            or doc.active_revision != revision
        ):
            raise EmbeddingError("DOCUMENT_CHANGED_DURING_INDEXING")
        store_vectors(db, missing, vectors, embedder, settings)
        doc.embedding_identity = identity
        job.status, job.stage, job.progress, job.error_code = "SUCCEEDED", "active", 100, None
        job.checkpoint = {
            **job.checkpoint,
            "embedding_batches": embedder.batch_results,
            "vectors_added": len(missing),
        }
        job.completed_at = datetime.now(UTC)
        db.commit()
        return "EMBEDDED" if missing else "UNCHANGED"
    except Exception as exc:
        db.rollback()
        job = db.get(IngestionJob, job_id)
        assert job is not None
        if job.checkpoint.get("lease_token") != lease:
            return "BUSY"
        job.status, job.error_code = (
            "FAILED",
            str(exc) if isinstance(exc, EmbeddingError) else "REEMBEDDING_FAILED",
        )
        job.completed_at = datetime.now(UTC)
        if embedder:
            job.checkpoint = {**job.checkpoint, "embedding_batches": embedder.batch_results}
        db.commit()
        return "FAILED"
