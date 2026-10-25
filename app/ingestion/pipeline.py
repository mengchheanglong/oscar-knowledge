import hashlib
import multiprocessing
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Chunk, Collection, Document, IngestionJob
from app.embeddings.provider import provider
from app.ingestion.chunking import chunk_segments
from app.ingestion.loaders import PARSER_VERSION, SourceError, load


def _extract_child(path, settings, connection):
    try:
        connection.send((True, load(Path(path), settings)))
    except Exception as exc:
        connection.send((False, str(exc) if isinstance(exc, SourceError) else "PARSER_FAILED"))
    finally:
        connection.close()


def extract_bounded(path: Path, settings: Settings):
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_extract_child, args=(str(path), settings, sender))
    process.start()
    sender.close()
    try:
        if not receiver.poll(settings.parser_timeout_seconds):
            raise SourceError("PARSER_TIMEOUT")
        ok, value = receiver.recv()
        if not ok:
            raise SourceError(value)
        return value
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        receiver.close()


def enqueue(db: Session, path: Path, collection: str, *, approved=False, **metadata):
    if path.is_symlink():
        raise SourceError("INVALID_FILE")
    path = path.resolve(strict=True)
    col = db.scalar(select(Collection).where(Collection.slug == collection))
    if not col:
        raise ValueError("UNKNOWN_COLLECTION")
    key = metadata.pop("canonical_key", None) or hashlib.sha256(str(path).encode()).hexdigest()
    # Serialize catalog updates for this collection, including concurrent new-document creation.
    db.execute(select(Collection).where(Collection.id == col.id).with_for_update())
    doc = db.scalar(
        select(Document).where(Document.collection_id == col.id, Document.canonical_key == key)
    )
    if not doc:
        doc = Document(
            collection_id=col.id,
            canonical_key=key,
            local_path=str(path),
            title=metadata.pop("title", path.stem),
            content_type=path.suffix.lower(),
            approved=approved,
            **metadata,
        )
        db.add(doc)
        db.flush()
    else:
        # Explicit curator approval is required on every submission; never silently resurrect deletes.
        if doc.status == "DELETED":
            raise ValueError("DOCUMENT_DELETED")
        doc.approved = approved
        doc.local_path = str(path)
    pending = db.scalar(
        select(IngestionJob).where(
            IngestionJob.document_id == doc.id, IngestionJob.status.in_(["QUEUED", "PROCESSING"])
        )
    )
    if pending:
        db.commit()
        return pending
    queued_count = (
        db.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .join(Document, IngestionJob.document_id == Document.id)
            .where(
                Document.collection_id == col.id, IngestionJob.status.in_(["QUEUED", "PROCESSING"])
            )
        )
        or 0
    )
    if queued_count >= get_settings().max_pending_jobs:
        raise SourceError("QUEUE_LIMIT")
    job = IngestionJob(document_id=doc.id, checkpoint={"metadata": metadata})
    db.add(job)
    doc.status = "QUEUED"
    db.commit()
    return job


def process_job(db: Session, job_id: uuid.UUID, settings: Settings, *, force=False):
    job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id).with_for_update())
    if not job:
        raise ValueError("UNKNOWN_JOB")
    now = datetime.now(UTC)
    if (
        job.status == "PROCESSING"
        and job.started_at
        and job.started_at > now - timedelta(seconds=settings.job_lease_seconds)
    ):
        db.rollback()
        return "BUSY"
    if job.status == "SUCCEEDED" and not force:
        db.rollback()
        return "SUCCEEDED"
    job.status, job.stage = "PROCESSING", "extract"
    job.attempts += 1
    job.started_at = now
    job.completed_at = None
    job.checkpoint = {**job.checkpoint, "restart": "from_source", "parser": PARSER_VERSION}
    db.commit()
    doc = db.get(Document, job.document_id)
    assert doc is not None
    embedder = None
    stage = "extract"
    try:
        # Transaction-scoped document lock prevents overlapping activation across jobs.
        doc = db.scalar(select(Document).where(Document.id == doc.id).with_for_update())
        assert doc is not None
        if not doc.approved or doc.status == "DELETED":
            raise SourceError("NOT_APPROVED_OR_DELETED")
        path = Path(doc.local_path)
        if path.is_symlink() or path.stat().st_size > settings.max_file_bytes:
            raise SourceError("FILE_TOO_LARGE_OR_UNSAFE")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        embedder = provider(settings)
        identity = embedder.identity if embedder else None
        if (
            not force
            and doc.content_sha256 == digest
            and doc.parser_version == PARSER_VERSION
            and doc.embedding_identity == identity
        ):
            for name, value in job.checkpoint.get("metadata", {}).items():
                setattr(doc, name, value)
            doc.status = "INDEXED"
            job.status, job.stage, job.progress = "SUCCEEDED", "unchanged", 100
            job.completed_at = now
            db.commit()
            return "UNCHANGED"
        segments = list(chunk_segments(extract_bounded(path, settings)))
        # Serialize global quota accounting before any new revision is inserted.
        db.execute(text("SELECT pg_advisory_xact_lock(7643921)"))
        used = db.scalar(select(func.coalesce(func.sum(Chunk.char_count), 0))) or 0
        if used + sum(len(s.text) for s in segments) > settings.max_storage_chars:
            raise SourceError("STORAGE_QUOTA")
        if len(segments) > 5000:
            raise SourceError("CHUNK_LIMIT")
        if embedder and len(segments) > 256:
            raise SourceError("EMBEDDING_DOCUMENT_BUDGET")
        stage = "embed" if embedder else "index"
        vectors: list[list[float] | None] = (
            list(embedder.embed([s.text for s in segments])) if embedder else [None] * len(segments)
        )
        revision = doc.active_revision + 1
        if embedder:
            job.checkpoint = {**job.checkpoint, "embedding_batches": embedder.batch_results}
        for ordinal, (segment, vector) in enumerate(zip(segments, vectors, strict=True)):
            db.add(
                Chunk(
                    id=uuid.uuid5(
                        doc.id, f"{revision}:{ordinal}:{digest}:{PARSER_VERSION}:{identity}"
                    ),
                    document_id=doc.id,
                    collection_id=doc.collection_id,
                    revision=revision,
                    ordinal=ordinal,
                    text=segment.text,
                    char_count=len(segment.text),
                    token_estimate=(len(segment.text) + 3) // 4,
                    heading_path=segment.heading_path,
                    page_start=segment.page_start,
                    page_end=segment.page_end,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    source_metadata=segment.metadata,
                    embedding=vector,
                    embedding_identity=identity,
                )
            )
        # Flush all chunks before atomically activating their revision.
        db.flush()
        doc.active_revision, doc.content_sha256 = revision, digest
        for name, value in job.checkpoint.get("metadata", {}).items():
            setattr(doc, name, value)
        doc.parser_version, doc.embedding_identity = PARSER_VERSION, identity
        doc.status, doc.error_code, doc.updated_at = "INDEXED", None, now
        job.status, job.stage, job.progress, job.error_code = "SUCCEEDED", "active", 100, None
        job.completed_at = datetime.now(UTC)
        db.commit()
        return "INDEXED"
    except Exception as exc:
        db.rollback()
        job = db.get(IngestionJob, job_id)
        assert job is not None
        doc = db.get(Document, job.document_id)
        assert doc is not None
        code = (
            str(exc)
            if isinstance(exc, (SourceError, ValueError))
            and re.fullmatch(r"[A-Z_]{1,80}", str(exc))
            else "INGESTION_FAILED"
        )
        job.stage = stage
        if embedder:
            job.checkpoint = {**job.checkpoint, "embedding_batches": embedder.batch_results}
        job.status = "SKIPPED" if code == "OCR_REQUIRED" else "FAILED"
        job.error_code, job.completed_at = code, datetime.now(UTC)
        if doc.status != "DELETED":
            doc.status, doc.error_code = job.status, code
        db.commit()
        return job.status
