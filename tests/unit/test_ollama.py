import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.embeddings.base import EmbeddingError
from app.embeddings.factory import provider
from app.embeddings.ollama_provider import OllamaEmbedding

DIGEST = "a" * 64


def settings(**kwargs):
    return Settings(
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=1024,
        embedding_model_revision=DIGEST,
        **kwargs,
    )


@pytest.fixture
def native(monkeypatch):
    calls = []
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda *a, **kw: httpx.Response(
            200, json={"models": [{"name": "qwen3-embedding:0.6b", "digest": DIGEST}]}
        ),
    )

    def post(self, url, **kwargs):
        calls.append((url, kwargs))
        inputs = kwargs["json"]["input"]
        return httpx.Response(
            200,
            json={
                "model": "qwen3-embedding:0.6b",
                "embeddings": [[1.0] + [0.0] * 1023 for _ in inputs],
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    return calls


def test_documents_queries_batching_and_no_paid_fallback(native):
    embedder = provider(settings(embedding_batch_size=2, embedding_api_key="must-not-be-sent"))
    assert embedder is not None
    assert len(embedder.embed_documents(["first", "second", "third"])) == 3
    assert native[0][1]["json"]["input"] == ["first", "second"]
    assert native[1][1]["json"]["input"] == ["third"]
    assert native[0][1]["json"]["truncate"] is False
    assert len(embedder.embed_query("pricing")) == 1024
    assert native[-1][1]["json"]["input"][0].startswith("Instruct: ")
    assert "\nQuery:pricing" in native[-1][1]["json"]["input"][0]
    assert all(
        url == "http://127.0.0.1:11434/api/embed" and not kwargs.get("headers")
        for url, kwargs in native
    )
    assert provider(Settings(embedding_api_key="unused-explicit-disabled")) is None


@pytest.mark.parametrize(
    "variant", ["dimensions", "missing", "zero", "nan", "infinity", "model", "wrong-count"]
)
def test_strict_response_validation(native, monkeypatch, variant):
    vector = [1.0] + [0.0] * 1023
    data = {"model": "qwen3-embedding:0.6b", "embeddings": [vector]}
    if variant == "dimensions":
        vector.pop()
    elif variant == "missing":
        data.pop("embeddings")
    elif variant == "zero":
        vector[0] = 0.0
    elif variant == "nan":
        vector[0] = float("nan")
    elif variant == "infinity":
        vector[0] = float("inf")
    elif variant == "model":
        data["model"] = "other-model"
    else:
        data["embeddings"] = []

    class Response:
        status_code = 200
        is_success = True

        def json(self):
            return data

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: Response())
    with pytest.raises(EmbeddingError):
        OllamaEmbedding(settings()).embed_documents(["x"])


@pytest.mark.parametrize("failure", ["connection", "timeout", 404, 401, 429, 503])
def test_failures_retry_bounded_and_never_change_provider(native, monkeypatch, failure):
    attempts = []
    monkeypatch.setattr("app.embeddings.base.time.sleep", lambda delay: None)

    def post(*args, **kwargs):
        attempts.append(1)
        if failure == "connection":
            raise httpx.ConnectError("private diagnostic must not escape")
        if failure == "timeout":
            raise httpx.ReadTimeout("private diagnostic must not escape")
        return httpx.Response(failure)

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(EmbeddingError, match="^EMBEDDING_") as error:
        OllamaEmbedding(settings()).embed_query("x")
    assert "private diagnostic" not in str(error.value)
    assert len(attempts) == (1 if failure in [401, 404] else 3)


def test_identity_includes_digest_preprocessing_and_instruction(native, monkeypatch):
    local = OllamaEmbedding(settings())
    docker = OllamaEmbedding(settings(ollama_base_url="http://host.docker.internal:11434"))
    assert local.identity == docker.identity
    assert local.identity != OllamaEmbedding(settings(ollama_query_instruction="")).identity
    assert "1024|raw-v1|query:" in local.identity and DIGEST in local.identity
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda *a, **kw: httpx.Response(
            200, json={"models": [{"name": "qwen3-embedding:0.6b", "digest": "b" * 64}]}
        ),
    )
    with pytest.raises(EmbeddingError, match="REVISION_MISMATCH"):
        local.embed_documents(["x"])


@pytest.mark.parametrize(
    "override",
    [
        {"embedding_dimensions": 1536},
        {"embedding_model": "qwen3-embedding:8b"},
        {"ollama_base_url": "https://remote.example.org"},
        {"ollama_base_url": "http://user:secret@localhost:11434"},
        {"embedding_batch_size": 100},
        {"embedding_model_revision": "unverified"},
    ],
)
def test_invalid_configuration(override):
    values = dict(
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_dimensions=1024,
    )
    values.update(override)
    with pytest.raises(ValidationError):
        Settings(**values)
