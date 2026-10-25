import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.embeddings.provider import OpenAICompatible
from app.ingestion.manifest import download
from app.retrieval.hybrid import rrf
from app.security import public_source_url


def test_rrf_deduplicates_deterministically():
    result = rrf([["b", "a", "a"], ["a", "c"]])
    assert result[0][0] == "a"
    assert result[0][1] == 1 / 62 + 1 / 61
    assert rrf([["b"], ["a"]]) == [("a", 1 / 61), ("b", 1 / 61)]


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/secret",
        "http://example.org",
        "https://user:pass@example.org/",
        "https://127.0.0.1/a",
        "https://localhost/a",
        "javascript:alert(1)",
    ],
)
def test_private_urls_rejected(url):
    assert public_source_url(url) is None


def test_citation_url_sanitizes_secrets():
    assert (
        public_source_url("https://example.org/lecture?token=secret#private")
        == "https://example.org/lecture"
    )


def test_download_allowlist(tmp_path):
    with pytest.raises(ValueError, match="DOWNLOAD_HOST"):
        download("https://evil.example/lecture.pdf", tmp_path / "test.pdf", Settings())


def test_fixed_dimension():
    with pytest.raises(ValidationError):
        Settings(embedding_dimensions=768)


@pytest.mark.parametrize("variant", ["dimensions", "count", "nan", "model", "zero"])
def test_invalid_embedding_response(monkeypatch, variant):
    vector = [1.0] * 1536
    payload = {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": vector}]}
    if variant == "dimensions":
        vector.pop()
    elif variant == "count":
        payload["data"] = []
    elif variant == "model":
        payload["model"] = "incompatible"
    elif variant == "nan":
        vector[0] = float("nan")
    else:
        vector[:] = [0.0] * 1536

    class FakeResponse:
        status_code = 200
        is_success = True

        def json(self):
            return payload

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: FakeResponse())
    with pytest.raises(ValueError, match="EMBEDDING"):
        OpenAICompatible(Settings()).embed(["synthetic"])


def test_embedding_reorders_by_index_and_does_not_retry_auth(monkeypatch):
    calls = []

    def post(*a, **kw):
        calls.append(1)
        return httpx.Response(401)

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(ValueError, match="HTTP_ERROR"):
        OpenAICompatible(Settings()).embed(["synthetic"])
    assert len(calls) == 1
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: httpx.Response(
            200,
            json={
                "model": "text-embedding-3-small",
                "data": [
                    {"index": 1, "embedding": [2.0] * 1536},
                    {"index": 0, "embedding": [1.0] * 1536},
                ],
            },
        ),
    )
    assert OpenAICompatible(Settings()).embed(["a", "b"])[0][0] == 1.0
