import base64
import hashlib
import hmac
import json
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.models import Chunk, Document, LibraryBook
from app.library.books import _prepare_pages, ingest_parts
from app.main import app

pytestmark = pytest.mark.integration


def make_scope(user_id: str, body_bytes: bytes, secret: str) -> str:
    now = int(time.time())
    claims = {
        "aud": "oscar-knowledge-private-v1",
        "sub": str(user_id),
        "iat": now,
        "exp": now + 30,
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def test_passage_inspection_security_and_revisions(db, tmp_path, monkeypatch):
    from tests.integration.test_library_books import resource

    # Create a private book with 2 chunks
    row = resource(tmp_path, pages=2)
    row["collection"] = "personal-library"
    state = _prepare_pages(row, tmp_path / "prepared-inspect", 10)
    ingest_parts(db, row, state, "personal-library", Settings(), limit=100)

    book = db.get(LibraryBook, row["id"])
    assert book is not None
    doc = db.query(Document).filter(Document.book_id == book.id).first()
    assert doc is not None
    chunk = db.query(Chunk).filter(Chunk.document_id == doc.id).first()
    assert chunk is not None

    owner_id = str(row["access"]["owner_id"])
    reader_id = str(uuid.uuid4())
    stranger_id = str(uuid.uuid4())

    # Set up reader grants file
    grants_path = tmp_path / "grants.json"
    grants_payload = {
        "version": 1,
        "grants": [
            {
                "reader_id": reader_id,
                "owner_id": owner_id,
                "book_ids": [row["id"]],
                "collections": ["personal-library"],
            }
        ],
    }
    grants_path.write_text(json.dumps(grants_payload))

    secret = "a" * 32
    monkeypatch.setenv("KNOWLEDGE_PRIVATE_READER_GRANTS_PATH", str(grants_path))
    monkeypatch.setenv("KNOWLEDGE_PRIVATE_SCOPE_SECRET", secret)
    monkeypatch.setenv("KNOWLEDGE_SERVICE_TOKEN", "test-token")

    from app.config import get_settings

    get_settings.cache_clear()

    client = TestClient(app)
    headers_base = {"Authorization": "Bearer test-token"}

    body = {
        "chunk_id": str(chunk.id),
        "document_id": str(doc.id),
        "revision": chunk.revision,
    }
    raw_body = json.dumps(body).encode()

    # 1. Unauthenticated -> 401
    assert client.post("/internal/v1/passage", json=body).status_code == 401

    # 2. Private book with service token alone (no scope header) -> 403 PRIVATE_SCOPE_REQUIRED
    res = client.post("/internal/v1/passage", json=body, headers=headers_base)
    assert res.status_code == 403
    assert res.json()["detail"] == "PRIVATE_SCOPE_REQUIRED"

    # 3. Private book with stranger scope (unauthorized cross-account) -> 403 PRIVATE_BOOK_NOT_PERMITTED
    stranger_scope = make_scope(stranger_id, raw_body, secret)
    res = client.post(
        "/internal/v1/passage",
        content=raw_body,
        headers={
            **headers_base,
            "Content-Type": "application/json",
            "X-OSCAR-Private-Scope": stranger_scope,
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "PRIVATE_BOOK_NOT_PERMITTED"

    # 4. Private book with valid reader grant -> 200 OK
    reader_scope = make_scope(reader_id, raw_body, secret)
    res = client.post(
        "/internal/v1/passage",
        content=raw_body,
        headers={
            **headers_base,
            "Content-Type": "application/json",
            "X-OSCAR-Private-Scope": reader_scope,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["chunk_id"] == str(chunk.id)
    assert data["document_id"] == str(doc.id)
    assert data["text"] == chunk.text
    assert data["char_count"] == len(chunk.text)
    assert data["revision"] == chunk.revision

    # 5. Stale revision request -> 409 STALE_REVISION (no silent substitution)
    stale_body = {**body, "revision": chunk.revision + 1}
    stale_raw = json.dumps(stale_body).encode()
    stale_scope = make_scope(reader_id, stale_raw, secret)
    res = client.post(
        "/internal/v1/passage",
        content=stale_raw,
        headers={
            **headers_base,
            "Content-Type": "application/json",
            "X-OSCAR-Private-Scope": stale_scope,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "STALE_REVISION"

    # 6. Arbitrary chunk ID not in document -> 404 CHUNK_NOT_FOUND
    mismatched_body = {**body, "document_id": str(uuid.uuid4())}
    mismatch_raw = json.dumps(mismatched_body).encode()
    mismatch_scope = make_scope(reader_id, mismatch_raw, secret)
    res = client.post(
        "/internal/v1/passage",
        content=mismatch_raw,
        headers={
            **headers_base,
            "Content-Type": "application/json",
            "X-OSCAR-Private-Scope": mismatch_scope,
        },
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "CHUNK_NOT_FOUND"

    # 7. Excluded chunk -> 410 CHUNK_EXCLUDED
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(
            service_token="test-token",
            private_scope_secret=secret,
            private_reader_grants_path=str(grants_path),
            quality_excluded_chunk_ids=[chunk.id],
        ),
    )
    res = client.post(
        "/internal/v1/passage",
        content=raw_body,
        headers={
            **headers_base,
            "Content-Type": "application/json",
            "X-OSCAR-Private-Scope": reader_scope,
        },
    )
    assert res.status_code == 410
    assert res.json()["detail"] == "CHUNK_EXCLUDED"
