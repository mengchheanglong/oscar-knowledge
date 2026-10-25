import hmac
import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from app.api.schemas import RetrievalRequest, RetrievalResponse
from app.config import get_settings
from app.db.models import Chunk, Collection, Document, LibraryBook
from app.db.session import session
from app.retrieval.hybrid import retrieve
from app.security import private_subject

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
            if version != "0005" or not vector:
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
    except Exception:
        logger.warning("RETRIEVAL_UNAVAILABLE")
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
                        LibraryBook.owner_id == subject,
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
