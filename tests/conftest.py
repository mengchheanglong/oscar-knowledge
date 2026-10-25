import os

import pytest
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def isolate_embedding_configuration(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_PROVIDER", "disabled")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_DIMENSIONS", "1536")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_MODEL_REVISION", "")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_API_KEY", "")
    get_settings.cache_clear()
    original = httpx.HTTPTransport.handle_request

    def no_external_http(self, request):
        if (
            os.getenv("KNOWLEDGE_TEST_LOCAL_MODEL") == "1"
            and request.url.host == "127.0.0.1"
            and request.url.port == 11434
        ):
            return original(self, request)
        raise AssertionError("External network is disabled in automated tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_external_http)
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db():
    url = os.getenv("KNOWLEDGE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("KNOWLEDGE_TEST_DATABASE_URL not configured")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Refusing integration tests outside a *_test database")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE chunk_embeddings, ingestion_jobs, chunks, documents"))
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()
