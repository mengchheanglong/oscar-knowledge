import time
import httpx
from app.embeddings.base import EmbeddingError, HttpEmbeddingBase, request_json, validate_vectors


class OpenAICompatible(HttpEmbeddingBase):
    name = "openai"

    def __init__(self, settings):
        super().__init__(settings)
        self.identity = self.make_identity(settings.embedding_model_revision or "unversioned")
        if not settings.embedding_model_revision:
            self.legacy_identity = (
                f"{settings.embedding_base_url.rstrip('/')}|{settings.embedding_model}|1536"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.batch_results = []
        results: list[list[float]] = []
        deadline = time.monotonic() + self.settings.embedding_document_timeout_seconds
        with httpx.Client(
            timeout=self.settings.embedding_timeout_seconds, follow_redirects=False, trust_env=False
        ) as client:
            for offset in range(0, len(texts), self.settings.embedding_batch_size):
                batch = texts[offset : offset + self.settings.embedding_batch_size]
                data, attempts = request_json(
                    client,
                    "POST",
                    self.settings.embedding_base_url.rstrip("/") + "/embeddings",
                    deadline=deadline,
                    timeout=self.settings.embedding_timeout_seconds,
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.embedding_api_key.get_secret_value()
                    },
                    payload={
                        "model": self.settings.embedding_model,
                        "dimensions": self.dimensions,
                        "input": batch,
                    },
                )
                if data.get("model") != self.settings.embedding_model:
                    raise EmbeddingError("EMBEDDING_MODEL_MISMATCH")
                items = data.get("data", [])
                if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                    raise EmbeddingError("EMBEDDING_INVALID_RESPONSE")
                if sorted(item.get("index", -1) for item in items) != list(range(len(batch))):
                    raise EmbeddingError("EMBEDDING_ORDER_OR_COUNT")
                vectors = [
                    item.get("embedding") for item in sorted(items, key=lambda item: item["index"])
                ]
                results.extend(validate_vectors(vectors, len(batch), self.dimensions))
                self.batch_results.append(
                    {
                        "offset": offset,
                        "count": len(batch),
                        "attempts": attempts,
                        "status": "SUCCEEDED",
                    }
                )
        return results
