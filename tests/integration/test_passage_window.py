import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.models import Chunk, Collection, Document, LibraryBook
from app.library.books import _prepare_pages, ingest_parts
from app.main import app
from tests.integration.test_passage_inspection import make_scope

pytestmark = pytest.mark.integration


def test_window_independent_neighbor_eligibility_and_exact_text(db, monkeypatch):
    collection = Collection(
        slug="window-synthetic-" + uuid.uuid4().hex[:8], title="Window", visibility="CURATED_SHARED"
    )
    other = Collection(
        slug="window-other-" + uuid.uuid4().hex[:8], title="Other", visibility="CURATED_SHARED"
    )
    db.add_all([collection, other])
    db.flush()
    document = Document(
        collection_id=collection.id,
        canonical_key="window",
        local_path="synthetic",
        title="Synthetic original",
        content_type=".md",
        approved=True,
        active_revision=2,
        status="INDEXED",
    )
    db.add(document)
    db.flush()
    chunks = []
    for ordinal in range(5):
        value = f"Original qualification {ordinal}: ខ្មែរ😀"
        chunk = Chunk(
            id=uuid.uuid4(),
            document_id=document.id,
            collection_id=collection.id,
            revision=2,
            ordinal=ordinal,
            text=value,
            char_count=len(value),
            token_estimate=10,
            heading_path="Synthetic section",
            page_start=ordinal + 1,
            page_end=ordinal + 1,
        )
        chunks.append(chunk)
    db.add_all(chunks)
    db.commit()
    settings = Settings(
        service_token="test-token",
        allowed_collections=[collection.slug],
        quality_excluded_chunk_ids=[chunks[1].id],
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    # A malformed neighbor cannot inherit the anchor's collection permission.
    chunks[3].collection_id = other.id
    db.commit()
    body = {
        "chunk_id": str(chunks[2].id),
        "document_id": str(document.id),
        "revision": 2,
        "radius": 2,
    }
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}
    assert client.post("/internal/v1/passage/window", json=body).status_code == 401
    response = client.post("/internal/v1/passage/window", json=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert {p["chunk_id"] for p in data["passages"]} == {str(chunks[i].id) for i in (0, 2, 4)}
    assert data["context_limited"]
    for p in data["passages"]:
        original = next(c for c in chunks if str(c.id) == p["chunk_id"])
        assert p["text"] == original.text
        assert p["char_count"] == len(original.text)
        assert p["text_sha256"] == hashlib.sha256(original.text.encode()).hexdigest()
    assert (
        client.post(
            "/internal/v1/passage/window", json={**body, "revision": 1}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/internal/v1/passage/window", json={**body, "radius": 3}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/internal/v1/passage/window", json={**body, "max_bytes": 1}, headers=headers
        ).status_code
        == 413
    )


def test_window_owner_reader_revocation_generation_and_body_binding(db, tmp_path, monkeypatch):
    from tests.integration.test_library_books import resource

    row = resource(tmp_path, pages=3)
    row["collection"] = "personal-library"
    prepared = _prepare_pages(row, tmp_path / "prepared-window", 10)
    ingest_parts(db, row, prepared, "personal-library", Settings(), limit=100)
    book = db.get(LibraryBook, row["id"])
    doc = db.query(Document).filter(Document.book_id == book.id).first()
    anchor = db.query(Chunk).filter(Chunk.document_id == doc.id).order_by(Chunk.ordinal).first()
    owner = str(book.owner_id)
    reader = str(uuid.uuid4())
    grants = tmp_path / "grants.json"
    grants.write_text(
        json.dumps(
            {
                "version": 1,
                "grants": [
                    {
                        "reader_id": reader,
                        "owner_id": owner,
                        "book_ids": [row["id"]],
                        "collections": ["personal-library"],
                    }
                ],
            }
        )
    )
    secret = "synthetic-window-scope-secret-1234567890"
    settings = Settings(
        service_token="test-token",
        private_scope_secret=secret,
        private_reader_grants_path=str(grants),
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    client = TestClient(app)
    body = {
        "chunk_id": str(anchor.id),
        "document_id": str(doc.id),
        "revision": anchor.revision,
        "radius": 1,
    }
    raw = json.dumps(body).encode()

    def headers(subject):
        return {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json",
            "X-OSCAR-Private-Scope": make_scope(subject, raw, secret),
        }

    for subject in (owner, reader):
        result = client.post("/internal/v1/passage/window", content=raw, headers=headers(subject))
        assert result.status_code == 200
        assert all(p["book_id"] == row["id"] for p in result.json()["passages"])
    assert (
        client.post(
            "/internal/v1/passage/window", content=raw, headers=headers(str(uuid.uuid4()))
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/internal/v1/passage/window", json={**body, "radius": 2}, headers=headers(reader)
        ).status_code
        == 403
    )
    grants.write_text(json.dumps({"version": 1, "grants": []}))
    assert (
        client.post("/internal/v1/passage/window", content=raw, headers=headers(reader)).status_code
        == 403
    )
    book.active_generation += 1
    db.commit()
    assert (
        client.post("/internal/v1/passage/window", content=raw, headers=headers(owner)).status_code
        == 409
    )
