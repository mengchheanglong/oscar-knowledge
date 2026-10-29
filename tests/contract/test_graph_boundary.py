from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


def test_graph_rejects_unsigned_private_access_and_unbounded_requests(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_SERVICE_TOKEN", "synthetic-graph-token")
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.post("/internal/v1/graph", json={}).status_code == 401
    headers = {"Authorization": "Bearer synthetic-graph-token"}
    assert (
        client.post(
            "/internal/v1/graph", json={"collection_ids": ["personal-library"]}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post("/internal/v1/graph", json={"limit": 10000}, headers=headers).status_code == 422
    )
    assert (
        client.post("/internal/v1/graph", json={"offset": -1}, headers=headers).status_code == 422
    )
