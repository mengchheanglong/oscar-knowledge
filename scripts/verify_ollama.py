"""Explicit real local-model check; never contacts a paid embedding provider."""

import json
import math
import time
from pathlib import Path

import httpx


def verify():
    root = Path("D:/AI/Ollama/models")
    before = {str(p.relative_to(root)): p.stat().st_size for p in root.rglob("*") if p.is_file()}
    texts = [
        "Competitive advantage allows firms to sustain superior performance.",
        "Pricing strategy affects demand and profitability.",
    ]
    with httpx.Client(base_url="http://127.0.0.1:11434", timeout=180, trust_env=False) as client:
        tag = next(
            item
            for item in client.get("/api/tags").json()["models"]
            if item["name"] == "qwen3-embedding:0.6b"
        )

        def embed(inputs):
            start = time.perf_counter()
            response = client.post(
                "/api/embed",
                json={
                    "model": tag["name"],
                    "input": inputs,
                    "truncate": False,
                    "keep_alive": "-1m",
                    "options": {"num_ctx": 4096},
                },
            )
            response.raise_for_status()
            data = response.json()
            vectors = data["embeddings"]
            assert len(vectors) == len(inputs)
            assert all(
                len(v) == 1024 and any(v) and all(math.isfinite(x) for x in v) for v in vectors
            )
            return vectors, time.perf_counter() - start

        first, cold = embed([texts[0]])
        batch, batch_time = embed(texts)
        second, warm = embed([texts[1]])

        def cosine(a, b):
            return sum(x * y for x, y in zip(a, b, strict=True)) / (
                math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
            )

        similarities = [cosine(first[0], batch[0]), cosine(second[0], batch[1])]
        assert min(similarities) > 0.999
        assert cosine(first[0], batch[1]) < similarities[0] - 0.01
        _, sixteen = embed(texts * 8)
        runtime = client.get("/api/ps").json()
    after = {str(p.relative_to(root)): p.stat().st_size for p in root.rglob("*") if p.is_file()}
    assert before == after, "Inference must not download model files"
    report = {
        "runtime": "Ollama",
        "model": tag["name"],
        "digest": tag["digest"],
        "dimensions": 1024,
        "model_path": str(root),
        "model_bytes": tag["size"],
        "first_measured_seconds": cold,
        "single_warm_seconds": warm,
        "batch_2_seconds": batch_time,
        "batch_16_seconds": sixteen,
        "batch_16_embeddings_per_second": 16 / sixteen,
        "batch_order_cosines": similarities,
        "model_files_unchanged_by_inference": True,
        "loaded_models": runtime["models"],
    }
    Path("docs/QWEN_RUNTIME_VERIFICATION.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    verify()
