"""Real HTTP retrieval verification. No generation or paid provider calls."""

import json
from pathlib import Path

import httpx

from app.config import get_settings


def main():
    settings = get_settings()
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=5) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.post("/internal/v1/retrieve", json={"query": "pricing"}).status_code == 401
        response = client.post(
            "/internal/v1/retrieve",
            headers={
                "Authorization": "Bearer " + settings.service_token.get_secret_value(),
            },
            json={
                "query": "subscription pricing",
                "collection_ids": ["mba-business"],
                "mode": "keyword",
                "top_k": 4,
            },
        )
        response.raise_for_status()
        data = response.json()
        assert data["retrieval_mode_used"] == "keyword"
        assert data["results"][0]["course_code"] == "DEMO-PRICING"
        assert data["results"][0]["locator"] == "Pricing experiments"
        assert "C:\\" not in response.text
        natural = client.post(
            "/internal/v1/retrieve",
            headers={
                "Authorization": "Bearer " + settings.service_token.get_secret_value(),
            },
            json={
                "query": "How should Rentify test its subscription pricing, using the synthetic course notes?",
                "mode": "keyword",
            },
        )
        natural.raise_for_status()
        assert natural.json()["results"][0]["course_code"] == "DEMO-PRICING"
        Path("docs/verified-evidence.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("PASS: readiness, auth, real HTTP keyword retrieval, fixture provenance and locator")


if __name__ == "__main__":
    main()
