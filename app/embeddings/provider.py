import math
import random
import time
from typing import Protocol

import httpx

from app.config import Settings


class EmbeddingProvider(Protocol):
    identity: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatible:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.identity = f"{settings.embedding_base_url.rstrip('/')}|{settings.embedding_model}|1536"
        self.batch_results: list[dict] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        self.batch_results = []
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            for offset in range(0, len(texts), 32):
                batch = texts[offset : offset + 32]
                for attempt in range(3):
                    try:
                        response = client.post(
                            self.settings.embedding_base_url.rstrip("/") + "/embeddings",
                            headers={
                                "Authorization": "Bearer "
                                + self.settings.embedding_api_key.get_secret_value()
                            },
                            json={
                                "model": self.settings.embedding_model,
                                "dimensions": 1536,
                                "input": batch,
                            },
                        )
                    except httpx.TransportError:
                        if attempt == 2:
                            raise ValueError("EMBEDDING_UNAVAILABLE") from None
                        time.sleep(2**attempt + random.random())
                        continue
                    if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 2:
                        time.sleep(2**attempt + random.random())
                        continue
                    if not response.is_success:
                        raise ValueError("EMBEDDING_HTTP_ERROR")
                    payload = response.json()
                    if payload.get("model") != self.settings.embedding_model:
                        raise ValueError("EMBEDDING_MODEL_MISMATCH")
                    data = payload.get("data", [])
                    if sorted(item.get("index", -1) for item in data) != list(range(len(batch))):
                        raise ValueError("EMBEDDING_ORDER_OR_COUNT")
                    for item in sorted(data, key=lambda d: d["index"]):
                        vector = item["embedding"]
                        if (
                            len(vector) != 1536
                            or any(
                                isinstance(v, bool)
                                or not isinstance(v, (int, float))
                                or not math.isfinite(v)
                                for v in vector
                            )
                            or not any(vector)
                        ):
                            raise ValueError("EMBEDDING_DIMENSION_OR_VALUE")
                        results.append(vector)
                    self.batch_results.append(
                        {
                            "offset": offset,
                            "count": len(batch),
                            "attempts": attempt + 1,
                            "status": "SUCCEEDED",
                        }
                    )
                    break
        return results


def provider(settings: Settings) -> OpenAICompatible | None:
    return OpenAICompatible(settings) if settings.embedding_api_key.get_secret_value() else None
