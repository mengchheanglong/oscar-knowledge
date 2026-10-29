import json
import uuid
from typing import Literal, cast
from pathlib import Path

import typer
from sqlalchemy import select, func

from app.api.schemas import RetrievalRequest
from app.config import get_settings
from app.db.models import Chunk, ChunkEmbedding, Collection, Document, IngestionJob
from app.embeddings.provider import provider
from app.ingestion.reembedding import enqueue_reembed
from app.db.session import session
from app.ingestion.loaders import SUPPORTED
from app.ingestion.manifest import import_manifest as submit_manifest
from app.ingestion.pipeline import enqueue, process_job
from app.library.cli import library_cli
from app.retrieval.hybrid import retrieve

cli = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
cli.add_typer(library_cli, name="library")


@cli.command("graph-build")
def graph_build():
    """Build the derived topic graph atomically; no source/vector changes."""
    from app.graph.service import rebuild

    with session() as db:
        typer.echo(
            json.dumps(rebuild(db, progress=lambda value: typer.echo(json.dumps(value), err=True)))
        )


@cli.command("create-collection")
def create_collection(slug: str, title: str):
    """Create an explicitly allowlisted curated shared collection; no private ACL claim."""
    import re

    settings = get_settings()
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", slug)
        or slug not in settings.allowed_collections
    ):
        raise typer.BadParameter("COLLECTION_NOT_ALLOWED")
    if not title.strip() or len(title) > 300:
        raise typer.BadParameter("INVALID_COLLECTION_TITLE")
    with session() as db:
        existing = db.scalar(select(Collection).where(Collection.slug == slug))
        if existing:
            typer.echo("UNCHANGED")
            return
        db.add(Collection(slug=slug, title=title.strip(), visibility="CURATED_SHARED"))
        db.commit()
        typer.echo("CREATED")


@cli.command()
def doctor():
    """Check explicit migrations, database and local service configuration."""
    from app.main import ready

    try:
        ready()
        typer.echo("Database: ready (migration 0007)")
    except Exception:
        typer.echo(
            "NOT_READY: check DB, alembic upgrade head and KNOWLEDGE_SERVICE_TOKEN", err=True
        )
        raise typer.Exit(1) from None
    settings = get_settings()
    typer.echo(f"Embedding provider: {settings.embedding_provider}")
    typer.echo(f"Model: {settings.embedding_model}; dimensions: {settings.embedding_dimensions}")
    embedder = provider(settings)
    if not embedder:
        typer.echo("Runtime: disabled (keyword only); compatible vectors: 0")
        return
    try:
        identity = embedder.identity
        if settings.embedding_provider == "ollama":
            import httpx
            import time
            from app.embeddings.ollama_provider import OllamaEmbedding

            assert isinstance(embedder, OllamaEmbedding)
            with httpx.Client(follow_redirects=False, trust_env=False) as client:
                embedder._verify_revision(client, time.monotonic() + 3)
        typer.echo(
            "Runtime: reachable"
            if settings.embedding_provider == "ollama"
            else "Runtime: explicitly configured (no paid probe)"
        )
        with session() as db:
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(ChunkEmbedding)
                    .join(Chunk, Chunk.id == ChunkEmbedding.chunk_id)
                    .join(Document, Document.id == Chunk.document_id)
                    .join(Collection, Collection.id == Document.collection_id)
                    .where(
                        ChunkEmbedding.identity == identity,
                        Chunk.revision == Document.active_revision,
                        Document.approved.is_(True),
                        Document.status != "DELETED",
                        Collection.slug.in_(settings.allowed_collections),
                    )
                )
                or 0
            )
        typer.echo(f"Indexed compatible vectors: {count}")
    except Exception:
        typer.echo(
            "Runtime: unreachable or incompatible model; keyword retrieval remains available",
            err=True,
        )
        raise typer.Exit(1) from None


@cli.command("ingest-dir")
def ingest_dir(
    directory: Path,
    collection: str = "mba-business",
    approve: bool = typer.Option(
        False, help="Curator confirms these files may be shared with all OSCAR users"
    ),
    queue_only: bool = False,
):
    """Import a bounded nonrecursive directory. Approval is explicit."""
    settings = get_settings()
    if not approve:
        raise typer.BadParameter("Pass --approve only for authorized curated shared material")
    paths = []
    for path in directory.iterdir():
        if path.suffix.lower() in SUPPORTED and path.is_file():
            paths.append(path)
            if len(paths) > settings.max_batch_files:
                raise typer.BadParameter("BATCH_LIMIT")
    with session() as db:
        for path in sorted(paths):
            job = enqueue(db, path, collection, approved=True)
            result = "QUEUED" if queue_only else process_job(db, job.id, settings)
            typer.echo(f"{job.id} {result}")


@cli.command("import-manifest")
def import_manifest(path: Path, download_approved: bool = False, queue_only: bool = False):
    """Import only approved manifest entries. Downloads require an additional opt-in."""
    with session() as db:
        for job in submit_manifest(db, path, get_settings(), download_approved):
            typer.echo(
                f"{job.id} " + ("QUEUED" if queue_only else process_job(db, job.id, get_settings()))
            )


@cli.command()
def worker(limit: int = typer.Option(20, min=1, max=100), retry_failed: bool = False):
    """Process a bounded batch; expired processing leases restart from the source."""
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import and_, or_

    settings = get_settings()
    with session() as db:
        statuses = ["QUEUED", "FAILED"] if retry_failed else ["QUEUED"]
        ids = list(
            db.scalars(
                select(IngestionJob.id)
                .where(
                    or_(
                        IngestionJob.status.in_(statuses),
                        and_(
                            IngestionJob.status == "PROCESSING",
                            IngestionJob.started_at
                            < datetime.now(UTC) - timedelta(seconds=settings.job_lease_seconds),
                        ),
                    )
                )
                .order_by(IngestionJob.created_at)
                .limit(limit)
            )
        )
        db.rollback()
        for job_id in ids:
            typer.echo(f"{job_id} {process_job(db, job_id, settings)}")


@cli.command()
def jobs():
    """Show the latest 100 jobs without private paths or document text."""
    with session() as db:
        for job in db.scalars(
            select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(100)
        ):
            typer.echo(
                f"{job.id} {job.status} {job.stage} {job.progress}% attempts={job.attempts} {job.error_code or ''}"
            )


@cli.command()
def sources():
    """Export bounded provenance metadata, excluding raw file paths."""
    with session() as db:
        for doc in db.scalars(select(Document).order_by(Document.id).limit(1000)):
            typer.echo(
                json.dumps(
                    {
                        "id": str(doc.id),
                        "title": doc.title,
                        "url": doc.source_url,
                        "revision": doc.active_revision,
                        "sha256": doc.content_sha256,
                        "license": doc.license_type,
                        "status": doc.status,
                    }
                )
            )


@cli.command()
def reindex(document_id: uuid.UUID = typer.Option(..., "--document-id")):
    """Create a fresh durable job; retain the old revision on failure."""
    with session() as db:
        doc = db.get(Document, document_id)
        if not doc or not doc.approved or doc.status == "DELETED":
            raise typer.BadParameter("DOCUMENT_NOT_AVAILABLE")
        slug = db.scalar(select(Collection.slug).where(Collection.id == doc.collection_id))
        assert slug is not None
        job = enqueue(
            db, Path(doc.local_path), slug, approved=True, canonical_key=doc.canonical_key
        )
        typer.echo(process_job(db, job.id, get_settings(), force=True))


@cli.command()
def query(
    question: str,
    collection: str = "mba-business",
    mode: str = "hybrid",
    top_k: int = 6,
):
    """Retrieve evidence; never generate a final answer."""
    with session() as db:
        result = retrieve(
            db,
            RetrievalRequest(
                query=question,
                collection_ids=[collection],
                mode=cast(Literal["keyword", "semantic", "hybrid"], mode),
                top_k=top_k,
            ),
            get_settings(),
        )
        typer.echo(result.model_dump_json(indent=2))


@cli.command()
def reembed(
    collection: str = "mba-business",
    document_id: uuid.UUID | None = None,
    limit: int = typer.Option(100, min=1, max=1000),
    queue_only: bool = False,
):
    """Embed active stored chunks with the selected model; preserve IDs and old vectors."""
    settings = get_settings()
    if settings.embedding_provider == "disabled":
        raise typer.BadParameter("Select an embedding provider explicitly before re-embedding")
    if collection not in settings.allowed_collections:
        raise typer.BadParameter("COLLECTION_NOT_ALLOWED")
    with session() as db:
        statement = (
            select(Document.id)
            .join(Collection, Collection.id == Document.collection_id)
            .where(
                Collection.slug == collection,
                Document.approved.is_(True),
                Document.status != "DELETED",
                Document.active_revision > 0,
            )
        )
        if document_id:
            statement = statement.where(Document.id == document_id)
        ids = list(db.scalars(statement.order_by(Document.id).limit(limit)))
        for doc_id in ids:
            job = enqueue_reembed(db, doc_id, settings)
            outcome = "QUEUED" if queue_only else process_job(db, job.id, settings)
            typer.echo(f"{doc_id} {job.id} {outcome}")


@cli.command("eval")
def evaluate(path: Path, mode: str = "keyword"):
    """Evaluate explicit gold canonical keys; fixture scores are not corpus benchmarks."""
    dataset = json.loads(path.read_text(encoding="utf-8"))
    hits, recall, reciprocal = [], [], []
    with session() as db:
        for item in dataset["questions"]:
            gold = set(
                db.scalars(
                    select(Document.id).where(Document.canonical_key.in_(item["source_keys"]))
                )
            )
            if len(gold) != len(item["source_keys"]):
                raise typer.BadParameter(
                    "GOLD_SOURCES_NOT_INDEXED: import fixtures/demo.yaml first"
                )
            response = retrieve(
                db,
                RetrievalRequest(
                    query=item["query"], mode=cast(Literal["keyword", "semantic", "hybrid"], mode)
                ),
                get_settings(),
            )
            found = [r.document_id for r in response.results]
            hits.append(int(bool(set(found) & gold)))
            recall.append(len(set(found) & gold) / len(gold))
            reciprocal.append(
                next((1 / rank for rank, doc_id in enumerate(found, 1) if doc_id in gold), 0)
            )
    typer.echo(
        json.dumps(
            {
                "dataset": dataset["name"],
                "questions": len(hits),
                "mode": mode,
                "Hit@6": sum(hits) / len(hits),
                "Recall@6": sum(recall) / len(recall),
                "MRR@6": sum(reciprocal) / len(reciprocal),
            }
        )
    )


@cli.command("eval-passages")
def evaluate_real_passages(
    path: Path,
    mode: str = "hybrid",
    output: Path | None = None,
):
    """Evaluate hash-pinned PDF passage labels, including explicit unanswerable queries."""
    from app.evaluation import PassageDataset, evaluate_passages

    if mode not in {"keyword", "semantic", "hybrid"}:
        raise typer.BadParameter("INVALID_RETRIEVAL_MODE")
    if path.stat().st_size > 1_000_000:
        raise typer.BadParameter("EVALUATION_DATASET_TOO_LARGE")
    dataset = PassageDataset.model_validate_json(path.read_text(encoding="utf-8"))
    with session() as db:
        report = evaluate_passages(
            db, dataset, get_settings(), cast(Literal["keyword", "semantic", "hybrid"], mode)
        )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2))


def main():
    try:
        cli()
    except Exception:
        typer.echo(
            "COMMAND_FAILED: check arguments, source permissions, migrations and database readiness. No secrets or source text logged.",
            err=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
