"""Shared bounded HTTP mechanics; no text or credentials in error messages."""

import hashlib
import math
import random
import threading
import time
from typing import Protocol, Any

import httpx

from app.config import Settings

LOCAL_INFERENCE_LOCK = threading.BoundedSemaphore(1)


class EmbeddingError(ValueError):
    pass


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    @property
    def identity(self) -> str: ...

    legacy_identity: str | None
    batch_results: list[dict]

    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...


def validate_vectors(vectors: Any, count: int, dimensions: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != count:
        raise EmbeddingError("EMBEDDING_ORDER_OR_COUNT")
    for vector in vectors:
        if (
            not isinstance(vector, list)
            or len(vector) != dimensions
            or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in vector
            )
            or not any(vector)
        ):
            raise EmbeddingError("EMBEDDING_DIMENSION_OR_VALUE")
    return vectors


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    deadline: float,
    timeout: float,
    payload=None,
    headers=None,
):
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EmbeddingError("EMBEDDING_TIMEOUT")
        try:
            if method == "POST":
                response = client.post(
                    url, json=payload, headers=headers, timeout=min(timeout, remaining)
                )
            else:
                response = client.get(url, timeout=min(timeout, remaining))
        except httpx.TransportError:
            if attempt == 2:
                raise EmbeddingError("EMBEDDING_UNAVAILABLE") from None
        else:
            if response.status_code == 404:
                raise EmbeddingError("EMBEDDING_MODEL_UNAVAILABLE")
            if response.status_code not in {408, 429, 500, 502, 503, 504}:
                if not response.is_success:
                    raise EmbeddingError("EMBEDDING_HTTP_ERROR")
                try:
                    data = response.json()
                except (ValueError, TypeError):
                    raise EmbeddingError("EMBEDDING_INVALID_RESPONSE") from None
                if not isinstance(data, dict):
                    raise EmbeddingError("EMBEDDING_INVALID_RESPONSE")
                return data, attempt + 1
            if attempt == 2:
                raise EmbeddingError("EMBEDDING_UNAVAILABLE")
        delay = min(0.25 * 2**attempt + random.random() * 0.1, max(0, deadline - time.monotonic()))
        time.sleep(delay)
    raise EmbeddingError("EMBEDDING_UNAVAILABLE")


class HttpEmbeddingBase:
    name = ""
    legacy_identity: str | None = None

    def __init__(self, settings: Settings):
        self.settings = settings
        self.dimensions = settings.embedding_dimensions
        self.batch_results: list[dict] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)

    def embed_query(self, query: str) -> list[float]:
        return self.embed([query])[0]

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def make_identity(self, revision: str, instruction: str = "") -> str:
        origin = (
            self.settings.ollama_base_url
            if self.name == "ollama"
            else self.settings.embedding_base_url
        )
        endpoint = (
            "local"
            if self.name == "ollama"
            else hashlib.sha256(origin.rstrip("/").encode()).hexdigest()[:16]
        )
        instruct = hashlib.sha256(instruction.encode()).hexdigest()[:16] if instruction else "none"
        return f"{self.name}|{self.settings.embedding_model}|{revision}|{self.dimensions}|raw-v1|query:{instruct}|endpoint:{endpoint}"
