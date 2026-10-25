import hmac
import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text

from app.api.schemas import RetrievalRequest, RetrievalResponse
from app.config import get_settings
from app.db.models import Collection
from app.db.session import session
from app.retrieval.hybrid import retrieve

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
            if version != "0001" or not vector:
                raise ValueError("MIGRATION_REQUIRED")
    except Exception:
        raise HTTPException(503, "NOT_READY") from None
    return {"status": "ready"}


@app.post("/internal/v1/retrieve", response_model=RetrievalResponse, dependencies=[Depends(auth)])
def retrieval(body: RetrievalRequest):
    try:
        with session() as db:
            return retrieve(db, body, get_settings())
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
