import time
import httpx
from app.embeddings.base import (
    EmbeddingError,
    HttpEmbeddingBase,
    LOCAL_INFERENCE_LOCK,
    request_json,
    validate_vectors,
)


class OllamaEmbedding(HttpEmbeddingBase):
    name = "ollama"

    def __init__(self, settings):
        super().__init__(settings)
        self._revision = (settings.embedding_model_revision or "").removeprefix("sha256:")

    def _verify_revision(self, client, deadline):
        data, _ = request_json(
            client,
            "GET",
            self.settings.ollama_base_url.rstrip("/") + "/api/tags",
            deadline=deadline,
            timeout=min(3, self.settings.embedding_timeout_seconds),
        )
        models = data.get("models", [])
        if not isinstance(models, list):
            raise EmbeddingError("EMBEDDING_INVALID_RESPONSE")
        model = next(
            (
                m
                for m in models
                if isinstance(m, dict) and m.get("name") == self.settings.embedding_model
            ),
            None,
        )
        if not model or not isinstance(model.get("digest"), str):
            raise EmbeddingError("EMBEDDING_MODEL_UNAVAILABLE")
        revision = model["digest"].removeprefix("sha256:")
        import re

        if not re.fullmatch(r"[a-f0-9]{64}", revision):
            raise EmbeddingError("EMBEDDING_INVALID_REVISION")
        if self._revision and revision != self._revision:
            raise EmbeddingError("EMBEDDING_MODEL_REVISION_MISMATCH")
        self._revision = revision

    @property
    def identity(self):
        if not self._revision:
            with httpx.Client(follow_redirects=False, trust_env=False) as client:
                self._verify_revision(
                    client, time.monotonic() + self.settings.embedding_query_timeout_seconds
                )
        return self.make_identity(self._revision, self.settings.ollama_query_instruction)

    def embed_query(self, query: str) -> list[float]:
        instruction = self.settings.ollama_query_instruction
        text = f"Instruct: {instruction}\nQuery:{query}" if instruction else query
        return self._embed([text], self.settings.embedding_query_timeout_seconds)[0]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, self.settings.embedding_document_timeout_seconds)

    def _embed(self, texts, budget):
        self.batch_results = []
        if not texts:
            return []
        deadline = time.monotonic() + budget
        if not LOCAL_INFERENCE_LOCK.acquire(
            timeout=min(budget, self.settings.embedding_timeout_seconds)
        ):
            raise EmbeddingError("EMBEDDING_BUSY")
        try:
            results = []
            with httpx.Client(follow_redirects=False, trust_env=False) as client:
                self._verify_revision(client, deadline)
                for offset in range(0, len(texts), self.settings.embedding_batch_size):
                    batch = texts[offset : offset + self.settings.embedding_batch_size]
                    data, attempts = request_json(
                        client,
                        "POST",
                        self.settings.ollama_base_url.rstrip("/") + "/api/embed",
                        deadline=deadline,
                        timeout=self.settings.embedding_timeout_seconds,
                        payload={
                            "model": self.settings.embedding_model,
                            "input": batch,
                            "truncate": False,
                            "keep_alive": self.settings.ollama_keep_alive,
                            "options": {"num_ctx": 4096},
                        },
                    )
                    if data.get("model") != self.settings.embedding_model:
                        raise EmbeddingError("EMBEDDING_MODEL_MISMATCH")
                    results.extend(
                        validate_vectors(data.get("embeddings"), len(batch), self.dimensions)
                    )
                    self.batch_results.append(
                        {
                            "offset": offset,
                            "count": len(batch),
                            "attempts": attempts,
                            "status": "SUCCEEDED",
                        }
                    )
            return results
        finally:
            LOCAL_INFERENCE_LOCK.release()
