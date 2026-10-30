import asyncio
import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def test_window_has_a_real_response_deadline_and_no_raw_provider_error(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(service_token="test-token"))
    monkeypatch.setattr("app.main.WINDOW_TIMEOUT_SECONDS", 0.01)

    async def slow_source(*args):
        await asyncio.sleep(0.1)
        raise RuntimeError("private upstream detail")

    monkeypatch.setattr("app.main.inspect_passage", slow_source)
    response = TestClient(app).post(
        "/internal/v1/passage/window",
        json={"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()), "revision": 1},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "WINDOW_DEADLINE_EXCEEDED"
    assert "private upstream detail" not in response.text
