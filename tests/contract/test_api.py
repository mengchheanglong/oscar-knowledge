import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(service_token="test-token"))
    return TestClient(app)


def test_health_and_auth(client):
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.post("/internal/v1/retrieve", json={"query": "pricing"}).status_code == 401
    assert (
        client.get(
            "/internal/v1/collections", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert "X-Request-ID" in client.get("/health/live").headers


@pytest.mark.parametrize(
    "body",
    [
        {"query": " "},
        {"query": "x" * 4001},
        {"query": "x", "top_k": 21},
        {"query": "x", "path": "C:/secret"},
        {"query": "x", "collection_ids": []},
    ],
)
def test_invalid_requests(client, body):
    assert (
        client.post(
            "/internal/v1/retrieve", json=body, headers={"Authorization": "Bearer test-token"}
        ).status_code
        == 422
    )


def test_body_limit(client):
    assert client.post("/internal/v1/retrieve", content=b"x" * 40000).status_code == 413


def test_scope_is_enforced_before_database(client):
    assert (
        client.post(
            "/internal/v1/retrieve",
            json={"query": "pricing", "collection_ids": ["private"]},
            headers={"Authorization": "Bearer test-token"},
        ).status_code
        == 403
    )


def test_service_token_alone_cannot_access_private_metadata_or_evidence(client):
    headers = {"Authorization": "Bearer test-token"}
    assert (
        client.post(
            "/internal/v1/retrieve",
            json={"query": "systems", "collection_ids": ["personal-library"]},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post("/internal/v1/library/collections", content="{}", headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            "/internal/v1/retrieve",
            json={"query": "systems", "owner_id": "someone"},
            headers=headers,
        ).status_code
        == 422
    )
