import json
from pathlib import Path

import typer

from app.library.catalog import atomic_json, catalog_lock, digest, read_catalog, refresh

library_cli = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@library_cli.command("sync")
def sync_library(
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
    verify_originals: bool = False,
):
    """Refresh ingestion snapshots from active DB rows, optionally hash original PDFs."""
    from app.db.session import session
    from app.library.status import sync_status

    with session() as db:
        typer.echo(json.dumps(sync_status(db, catalog_dir, verify_originals=verify_originals)))


def resources(value):
    return value["resources"] + value.get("virtual_books", [])


@library_cli.command("scan")
def scan_library(
    root: list[Path] = typer.Option(..., help="Repeat for each existing source root"),
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
    dry_run: bool = True,
    verify_hashes: bool = False,
):
    """Read-only source scan. Dry-run writes nothing, including catalog output."""
    result = refresh(root, catalog_dir, dry_run=dry_run, verify=verify_hashes)
    typer.echo(
        json.dumps(
            {
                "resources": len(result["resources"]),
                "events": result["events"],
                "errors": len(result["errors"]),
                "source_files_modified": 0,
                "dry_run": dry_run,
            }
        )
    )


@library_cli.command("catalog")
def catalog_library(
    root: list[Path] = typer.Option(...),
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
    verify_hashes: bool = False,
):
    """Refresh the local catalog and generated views; never ingest or rename files."""
    result = refresh(root, catalog_dir, verify=verify_hashes)
    typer.echo(
        json.dumps(
            {
                "resources": len(result["resources"]),
                "events": result["events"],
                "errors": len(result["errors"]),
                "source_files_modified": 0,
            }
        )
    )


@library_cli.command("review")
def review_resource(
    resource_id: str,
    evidence: str = typer.Option(..., min=10, max=4000),
    shared: bool = typer.Option(
        False, help="Explicitly authorize reviewed bytes for shared retrieval"
    ),
    owner_id: str | None = typer.Option(
        None, help="Private owner UUID from authenticated OSCAR account"
    ),
    collection: str | None = typer.Option(
        None, help="Required allowlisted target for a shared grant"
    ),
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
):
    """Record a curator's rights decision, not ownership inferred from possession."""
    from datetime import UTC, datetime

    import uuid

    if bool(shared) == bool(owner_id):
        raise typer.BadParameter("Choose --shared or an explicit --owner-id, not both")
    if owner_id:
        owner_id = str(uuid.UUID(owner_id))
    from app.config import get_settings

    if shared and (
        not collection
        or collection not in get_settings().allowed_collections
        or collection in get_settings().private_collections
    ):
        raise typer.BadParameter("EXPLICIT_SHARED_COLLECTION_REQUIRED")
    with catalog_lock(catalog_dir):
        value = read_catalog(catalog_dir / "library.json")
        row = next(r for r in resources(value) if r["id"] == resource_id)
        if digest(Path(row["absolute_path"])) != row["sha256"]:
            raise typer.BadParameter("SOURCE_CHECKSUM_CHANGED_REFRESH_CATALOG")
        row["rights"] = {
            "local_possession": True,
            "permission_status": "APPROVED",
            "permitted_uses": [
                "local_index",
                "shared_retrieval" if shared else "private_retrieval",
            ],
            "approved_sha256": row["sha256"],
            "evidence": evidence,
            "reviewed_at": datetime.now(UTC).isoformat(),
        }
        row["access"] = {
            "visibility": "CURATED_SHARED" if shared else "PRIVATE",
            "owner_id": owner_id,
        }
        row["catalog_status"] = "APPROVED"
        if shared:
            row["collection"] = collection
        from app.db.models import Collection, LibraryBook
        from app.db.session import session

        with session() as db:
            book = db.get(LibraryBook, uuid.UUID(resource_id), with_for_update=True)
            if book:
                current_collection = db.get(Collection, book.collection_id)
                if (
                    (str(book.owner_id) if book.owner_id else None) != owner_id
                    or book.visibility != row["access"]["visibility"]
                    or not current_collection
                    or current_collection.slug != row["collection"]
                ):
                    raise typer.BadParameter("OWNERSHIP_OR_COLLECTION_TRANSFER_NOT_SUPPORTED")
            atomic_json(catalog_dir / "library.json", value)
            if book and not book.approved:
                book.approved, book.status = True, "REVIEWED_PENDING_INDEX"
                db.commit()
    typer.echo("APPROVED_REVIEWED_BYTES_ONLY")


@library_cli.command("prepare-book")
def prepare_book(
    resource_id: str,
    page_batch: int = typer.Option(40, min=1, max=100),
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
):
    """Prepare at most page-batch pages. Repeat until complete; no embeddings."""
    from app.library.books import prepare

    value = read_catalog(catalog_dir / "library.json")
    row = next(r for r in resources(value) if r["id"] == resource_id)
    state = prepare(row, catalog_dir / "ingestion-cache", page_batch=page_batch)
    typer.echo(json.dumps({k: v for k, v in state.items() if k not in {"parts", "pending_pages"}}))


@library_cli.command("ingest-book")
def ingest_book(
    resource_id: str,
    collection: str = typer.Option(...),
    limit: int = typer.Option(10, min=1, max=100),
    allow_partial: bool = typer.Option(
        False, help="Publish available pages with explicit unresolved-image coverage status"
    ),
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
):
    """Process approved scoped parts; activate only when every expected part exists."""
    from app.config import get_settings
    from app.db.session import session
    from app.library.books import ingest_parts

    value = read_catalog(catalog_dir / "library.json")
    row = next(r for r in resources(value) if r["id"] == resource_id)
    state_path = (
        catalog_dir
        / "ingestion-cache"
        / row["id"]
        / row["sha256"]
        / "bookparts-v2"
        / "preparation.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Do not hold the metadata writer lock over embedding work: revoke must be
    # able to persist its deny tombstone while a CLI batch is running.
    with session() as db:
        result = ingest_parts(
            db, row, state, collection, get_settings(), limit=limit, allow_partial=allow_partial
        )
    with catalog_lock(catalog_dir):
        value = read_catalog(catalog_dir / "library.json")
        current = next(r for r in resources(value) if r["id"] == resource_id)
        if (
            current["sha256"] == row["sha256"]
            and current["rights"]["permission_status"] == "APPROVED"
        ):
            current["ingestion"] = {
                **result,
                "source_sha256": row["sha256"],
                "indexed_revision": result.get("generation"),
                "parser_version": "bookparts-v2",
            }
            atomic_json(catalog_dir / "library.json", value)
    typer.echo(json.dumps(result))


@library_cli.command("revoke")
def revoke_resource(
    resource_id: str, catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog"))
):
    """Immediately gate indexed book evidence off, retaining all files and vectors."""
    from app.config import get_settings
    from app.db.session import session
    from app.library.books import revoke_book

    with catalog_lock(catalog_dir):
        value = read_catalog(catalog_dir / "library.json")
        row = next(r for r in resources(value) if r["id"] == resource_id)
        with session() as db:
            revoke_book(db, row, get_settings())
        row["rights"].update(permission_status="REVOKED", permitted_uses=[])
        row["catalog_status"] = "NEEDS_PERMISSION_REVIEW"
        row["ingestion"]["status"] = "REVOKED"
        atomic_json(catalog_dir / "library.json", value)
    typer.echo("REVOKED_FILES_AND_VECTORS_RETAINED")


@library_cli.command("register-range")
def register_range(
    parent_id: str,
    first_page: int = typer.Option(..., min=1),
    last_page: int = typer.Option(..., min=1),
    title: str | None = typer.Option(None),
    catalog_dir: Path = typer.Option(Path("D:/AI/OSCAR/Knowledge/Catalog")),
):
    """Reference a bounded physical PDF range without creating a source-file copy."""
    import uuid
    import pymupdf

    if not first_page <= last_page or last_page - first_page + 1 > 2000:
        raise typer.BadParameter("RANGE_PAGE_BUDGET")
    with catalog_lock(catalog_dir):
        value = read_catalog(catalog_dir / "library.json")
        parent = next(r for r in value["resources"] if r["id"] == parent_id)
        if parent["format"] != "pdf" or parent["access"]["visibility"] != "PRIVATE":
            raise typer.BadParameter("PRIVATE_PDF_PARENT_REQUIRED")
        if (
            parent["rights"]["permission_status"] != "APPROVED"
            or parent["rights"].get("approved_sha256") != parent["sha256"]
        ):
            raise typer.BadParameter("PARENT_PERMISSION_REQUIRED")
        if digest(Path(parent["absolute_path"])) != parent["sha256"]:
            raise typer.BadParameter("SOURCE_CHECKSUM_CHANGED")
        with pymupdf.open(parent["absolute_path"]) as pdf:
            if last_page > len(pdf):
                raise typer.BadParameter("PDF_RANGE_OUT_OF_BOUNDS")
        identifier = str(uuid.uuid5(uuid.UUID(parent_id), f"range:{first_page}:{last_page}"))
        if any(r["id"] == identifier for r in value.get("virtual_books", [])):
            typer.echo("UNCHANGED")
            return
        reference = {
            **parent,
            "id": identifier,
            "parent_resource_id": parent_id,
            "page_range": [first_page, last_page],
            "pdf_pages": last_page - first_page + 1,
            "title": (title or f"{parent['title']} — PDF pages {first_page}–{last_page}")[:500],
            "authors": [],
            "edition": None,
            "metadata_status": "NEEDS_METADATA_REVIEW",
            "ingestion": {"status": "CATALOGED"},
        }
        value.setdefault("virtual_books", []).append(reference)
        atomic_json(catalog_dir / "library.json", value)
        typer.echo(identifier)
