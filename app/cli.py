import json
import uuid
from typing import Literal, cast
from pathlib import Path

import typer
from sqlalchemy import select

from app.api.schemas import RetrievalRequest
from app.config import get_settings
from app.db.models import Collection, Document, IngestionJob
from app.db.session import session
from app.ingestion.loaders import SUPPORTED
from app.ingestion.manifest import import_manifest as submit_manifest
from app.ingestion.pipeline import enqueue, process_job
from app.retrieval.hybrid import retrieve

cli = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@cli.command()
def doctor():
    """Check explicit migrations, database and local service configuration."""
    from app.main import ready

    try:
        typer.echo(ready())
        typer.echo(
            "Embeddings: configured"
            if get_settings().embedding_api_key.get_secret_value()
            else "Embeddings: disabled (keyword only)"
        )
    except Exception:
        typer.echo(
            "NOT_READY: check DB, alembic upgrade head and KNOWLEDGE_SERVICE_TOKEN", err=True
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


@cli.command("eval")
def evaluate(path: Path):
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
                db, RetrievalRequest(query=item["query"], mode="keyword"), get_settings()
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
                "Hit@6": sum(hits) / len(hits),
                "Recall@6": sum(recall) / len(recall),
                "MRR@6": sum(reciprocal) / len(reciprocal),
            }
        )
    )


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
