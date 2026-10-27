import hmac
import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

import re

from app.api.schemas import (
    PassageInspectRequest,
    PassageInspectResponse,
    RetrievalRequest,
    RetrievalResponse,
)
from app.config import get_settings
from app.db.models import Chunk, Collection, Document, LibraryBook
from app.db.session import session
from app.library.access import can_read_private_book, private_book_access
from app.retrieval.hybrid import retrieve
from app.security import private_subject, public_source_url

app = FastAPI(title="OSCAR Knowledge", version="0.1.0")
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger("knowledge")


def auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    expected = get_settings().service_token.get_secret_value()
    supplied = credentials.credentials if credentials else ""
    if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(401, "SERVICE_AUTH_REQUIRED")


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    request_id = str(uuid.uuid4())
    if request.url.path.startswith("/internal/"):
        # Bound chunked bodies as well as Content-Length, before JSON parsing.
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 32768:
                from starlette.responses import JSONResponse

                return JSONResponse({"detail": "BODY_TOO_LARGE"}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    try:
        if not get_settings().service_token.get_secret_value():
            raise ValueError("TOKEN_REQUIRED")
        with session() as db:
            version = db.scalar(text("SELECT version_num FROM alembic_version"))
            vector = db.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            if version != "0006" or not vector:
                raise ValueError("MIGRATION_REQUIRED")
    except Exception:
        raise HTTPException(503, "NOT_READY") from None
    return {"status": "ready"}


@app.post("/internal/v1/retrieve", response_model=RetrievalResponse, dependencies=[Depends(auth)])
async def retrieval(body: RetrievalRequest, request: Request):
    try:
        settings = get_settings()
        subject = None
        if set(body.collection_ids) & set(settings.private_collections):
            subject = private_subject(
                request.headers.get("X-OSCAR-Private-Scope"),
                await request.body(),
                settings.private_scope_secret.get_secret_value(),
            )

        def scoped_retrieve():
            with session() as db:
                return retrieve(db, body, settings, subject=subject)

        return await run_in_threadpool(scoped_retrieve)
    except PermissionError:
        raise HTTPException(403, "COLLECTION_NOT_ALLOWED") from None
    except Exception as error:
        # Exception messages/SQL can contain private query text; log only the class.
        logger.warning("RETRIEVAL_UNAVAILABLE %s", type(error).__name__)
        raise HTTPException(503, "RETRIEVAL_UNAVAILABLE") from None


@app.get("/internal/v1/collections", dependencies=[Depends(auth)])
def collections():
    try:
        with session() as db:
            rows = db.scalars(
                select(Collection).where(
                    Collection.slug.in_(get_settings().allowed_collections),
                    Collection.visibility == "CURATED_SHARED",
                )
            ).all()
            return [{"id": c.slug, "title": c.title, "description": c.description} for c in rows]
    except Exception:
        raise HTTPException(503, "CATALOG_UNAVAILABLE") from None


@app.post("/internal/v1/library/collections", dependencies=[Depends(auth)])
async def library_collections(request: Request):
    """User-scoped counts only; no private titles, paths or owner identifiers."""
    settings = get_settings()
    try:
        subject = private_subject(
            request.headers.get("X-OSCAR-Private-Scope"),
            await request.body(),
            settings.private_scope_secret.get_secret_value(),
        )
    except PermissionError:
        raise HTTPException(403, "PRIVATE_SCOPE_REQUIRED") from None

    def scoped_counts():
        with session() as db:
            result = []
            active_chunks = (
                select(Chunk.id)
                .join(Document, Chunk.document_id == Document.id)
                .where(
                    Document.book_id == LibraryBook.id,
                    Document.book_generation == LibraryBook.active_generation,
                    Document.approved.is_(True),
                    Document.status != "DELETED",
                    Chunk.revision == Document.active_revision,
                )
                .exists()
            )
            for slug in settings.private_collections:
                count = db.scalar(
                    select(func.count())
                    .select_from(LibraryBook)
                    .join(Collection)
                    .where(
                        Collection.slug == slug,
                        Collection.visibility == "PRIVATE",
                        private_book_access(subject, settings),
                        LibraryBook.visibility == "PRIVATE",
                        LibraryBook.approved.is_(True),
                        LibraryBook.active_generation > 0,
                        LibraryBook.status.in_(["INDEXED", "PARTIALLY_INDEXED"]),
                        active_chunks,
                    )
                )
                result.append({"id": slug, "indexed_books": count or 0})
            return result

    return await run_in_threadpool(scoped_counts)


@app.post(
    "/internal/v1/passage",
    response_model=PassageInspectResponse,
    dependencies=[Depends(auth)],
)
async def inspect_passage(body: PassageInspectRequest, request: Request):
    settings = get_settings()
    raw_body = await request.body()
    scope_header = request.headers.get("X-OSCAR-Private-Scope")

    def perform_inspection():
        with session() as db:
            chunk = (
                db.query(Chunk)
                .filter(
                    Chunk.id == body.chunk_id,
                    Chunk.document_id == body.document_id,
                )
                .first()
            )
            if not chunk:
                raise HTTPException(404, "CHUNK_NOT_FOUND")

            if chunk.id in settings.quality_excluded_chunk_ids:
                raise HTTPException(410, "CHUNK_EXCLUDED")

            doc = db.query(Document).filter(Document.id == body.document_id).first()
            if not doc:
                raise HTTPException(404, "DOCUMENT_NOT_FOUND")

            if doc.status == "DELETED":
                raise HTTPException(410, "DOCUMENT_DELETED")

            if not doc.approved:
                raise HTTPException(403, "DOCUMENT_NOT_APPROVED")

            # Revision check: must match both chunk revision and document active revision
            if body.revision != chunk.revision or chunk.revision != doc.active_revision:
                raise HTTPException(409, "STALE_REVISION")

            coll = db.query(Collection).filter(Collection.id == doc.collection_id).first()
            if not coll:
                raise HTTPException(404, "COLLECTION_NOT_FOUND")

            book_record = None
            if doc.book_id:
                book_record = db.query(LibraryBook).filter(LibraryBook.id == doc.book_id).first()
                if (
                    not book_record
                    or not book_record.approved
                    or book_record.status not in ["INDEXED", "PARTIALLY_INDEXED"]
                ):
                    raise HTTPException(403, "BOOK_NOT_APPROVED")
                if (
                    book_record.active_generation <= 0
                    or doc.book_generation != book_record.active_generation
                ):
                    raise HTTPException(409, "STALE_BOOK_GENERATION")

            if coll.visibility == "CURATED_SHARED":
                if coll.slug not in settings.allowed_collections:
                    raise HTTPException(403, "COLLECTION_NOT_ALLOWED")
            elif coll.visibility == "PRIVATE":
                try:
                    subject = private_subject(
                        scope_header,
                        raw_body,
                        settings.private_scope_secret.get_secret_value(),
                    )
                except PermissionError:
                    raise HTTPException(403, "PRIVATE_SCOPE_REQUIRED") from None

                if book_record:
                    if not can_read_private_book(book_record, coll.slug, subject, settings):
                        raise HTTPException(403, "PRIVATE_BOOK_NOT_PERMITTED")
                else:
                    raise HTTPException(403, "PRIVATE_ACCESS_REQUIRES_BOOK")
            else:
                raise HTTPException(403, "COLLECTION_VISIBILITY_UNKNOWN")

            locators = []
            if chunk.page_start is not None:
                locators.append(
                    f"{'PDF page' if doc.book_id and doc.content_type == '.pdf' else 'Page'} {chunk.page_start}"
                    + (f"–{chunk.page_end}" if chunk.page_end != chunk.page_start else "")
                )
            if chunk.heading_path:
                locators.append(chunk.heading_path)
            if chunk.start_ms is not None:
                locators.append(f"{chunk.start_ms}–{chunk.end_ms} ms")

            meta = chunk.source_metadata or {}
            extraction = meta.get("extraction")
            formula_review = meta.get("formula_review_required")
            is_quant_or_math = bool(
                re.search(
                    r"\b(quant|quantitative|statistics|mathematics|accounting|calculus|physics|compilation)\b",
                    doc.title,
                    re.I,
                )
            )
            review_required = bool(
                extraction
                in {"LOCAL_TESSERACT_OCR", "VISUAL_DESCRIPTION", "VISUALLY_REVIEWED_TRANSCRIPTION"}
                or (formula_review and is_quant_or_math)
            )

            coverage_note = (
                " ".join(
                    filter(
                        None,
                        [
                            "Some image-only pages remain unindexed; consult original PDF."
                            if book_record and book_record.status == "PARTIALLY_INDEXED"
                            else None,
                            meta.get("source_notice"),
                        ],
                    )
                )
                or None
            )

            return PassageInspectResponse(
                chunk_id=chunk.id,
                document_id=doc.id,
                collection_id=coll.slug,
                title=doc.title,
                book_id=doc.book_id,
                author=doc.author,
                edition=meta.get("edition"),
                chapter=chunk.heading_path if doc.book_id else None,
                locator=" / ".join(locators) or None,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                revision=chunk.revision,
                text=chunk.text,
                char_count=len(chunk.text),
                extraction=extraction,
                review_required=review_required,
                coverage_note=coverage_note,
                source_url=public_source_url(doc.source_url),
                is_truncated=len(chunk.text) > 240,
            )

    return await run_in_threadpool(perform_inspection)
