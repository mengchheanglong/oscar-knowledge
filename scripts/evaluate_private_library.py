"""Real read-only scoped retrieval sample and local embedding probe; no answer generation."""

import base64
import hashlib
import hmac
import json
import statistics
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Chunk, Document, LibraryBook
from app.db.session import session
from app.embeddings.provider import provider
from app.library.catalog import atomic_json, read_catalog

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")
QUESTIONS = [
    (
        "strategy",
        "thinking_in_systems",
        "Which leverage points change feedback loops, rules and goals in a system?",
    ),
    (
        "finance",
        "psychology_of_money",
        "Why do investors need a margin of safety and room for error in long-term financial planning?",
    ),
    (
        "quantitative",
        "quant bible",
        "How is conditional probability calculated from the joint probability and the conditioning event?",
    ),
    (
        "product",
        "the_mom_test",
        "Why should founders ask about customers past behavior rather than pitch an idea or ask hypothetical questions?",
    ),
    (
        "leadership",
        "the_checklist_manifesto",
        "Why can short checklists improve reliability in complex team operations?",
    ),
    (
        "communication",
        "do_i_make_myself_clear",
        "How do plain words and shorter sentences improve clarity in professional writing?",
    ),
]


def main():
    settings = get_settings()
    owner = json.loads((ROOT / "private-use-approval.json").read_text(encoding="utf-8"))["owner_id"]
    resources = read_catalog(ROOT / "library.json")["resources"]
    key = settings.private_scope_secret.get_secret_value()
    bearer = {
        "Authorization": "Bearer " + settings.service_token.get_secret_value(),
        "Content-Type": "application/json",
    }

    def call(client, data, *, actor=owner, signed=True, expired=False, endpoint="retrieve"):
        body = json.dumps(data, separators=(",", ":")).encode()
        headers = dict(bearer)
        if signed:
            now = int(time.time()) - (60 if expired else 0)
            claims = {
                "aud": "oscar-knowledge-private-v1",
                "sub": actor,
                "iat": now,
                "exp": now + 30,
                "body_sha256": hashlib.sha256(body).hexdigest(),
            }
            payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
            headers["X-OSCAR-Private-Scope"] = (
                payload + "." + hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
            )
        return client.post(
            "http://127.0.0.1:8010/internal/v1/" + endpoint, content=body, headers=headers
        )

    results = []
    with httpx.Client(timeout=25, trust_env=False) as client:
        for category, marker, query in QUESTIONS:
            row = next(r for r in resources if marker in r["filename"].lower())
            with session() as db:
                book = db.get(LibraryBook, uuid.UUID(row["id"]))
                assert (
                    book
                    and book.approved
                    and book.active_generation > 0
                    and book.status in {"INDEXED", "PARTIALLY_INDEXED"}
                ), "EVALUATION_SOURCE_NOT_READY"
            for mode in ["keyword", "semantic", "hybrid"]:
                start = time.monotonic()
                response = call(
                    client,
                    {
                        "query": query,
                        "collection_ids": ["personal-library"],
                        "mode": mode,
                        "top_k": 5,
                    },
                )
                elapsed = time.monotonic() - start
                if response.status_code != 200:
                    results.append(
                        {
                            "category": category,
                            "mode_requested": mode,
                            "status": "UNAVAILABLE",
                            "http_status": response.status_code,
                            "seconds": elapsed,
                        }
                    )
                    continue
                data = response.json()
                found = [str(h.get("book_id")) for h in data["results"]]
                rank = next(
                    (n for n, identifier in enumerate(found, 1) if identifier == row["id"]), None
                )
                # One explicit gold book per question. These are book-level
                # sample metrics, not all relevant passages or academic mastery.
                results.append(
                    {
                        "category": category,
                        "query": query,
                        "mode_requested": mode,
                        "mode_used": data["retrieval_mode_used"],
                        "fallback": data.get("fallback_reason"),
                        "status": "PASS",
                        "seconds": round(elapsed, 4),
                        "gold_book_id": row["id"],
                        "hit_at_5": int(rank is not None),
                        "recall_at_5": int(rank is not None),
                        "reciprocal_rank_at_5": 1 / rank if rank else 0,
                        "hits": [
                            {
                                k: h.get(k)
                                for k in [
                                    "book_id",
                                    "chunk_id",
                                    "title",
                                    "page_start",
                                    "locator",
                                    "score",
                                ]
                            }
                            for h in data["results"]
                        ],
                    }
                )
                with session() as db:
                    for hit in data["results"]:
                        chunk = db.get(Chunk, uuid.UUID(hit["chunk_id"]))
                        doc = db.get(Document, chunk.document_id)
                        book = db.get(LibraryBook, doc.book_id)
                        assert (
                            str(book.owner_id) == owner
                            and book.approved
                            and doc.book_generation == book.active_generation
                        )
                        assert chunk.revision == doc.active_revision
                        assert "D:\\AI\\OSCAR" not in json.dumps(hit)
        request = {
            "query": "systems feedback",
            "collection_ids": ["personal-library"],
            "mode": "keyword",
            "top_k": 5,
        }
        assert call(client, request, signed=False).status_code == 403
        assert call(client, request, expired=True).status_code == 403
        other = call(client, request, actor=str(uuid.uuid4()))
        other.raise_for_status()
        assert not other.json()["results"]
        assert call(client, {}, signed=False, endpoint="library/collections").status_code == 403
        other_catalog = call(client, {}, actor=str(uuid.uuid4()), endpoint="library/collections")
        other_catalog.raise_for_status()
        assert all(c["indexed_books"] == 0 for c in other_catalog.json())
        shared = call(client, {**request, "collection_ids": ["mba-majors"]}, signed=False)
        shared.raise_for_status()
        assert all(h.get("book_id") is None for h in shared.json()["results"])
        public = client.get("http://127.0.0.1:8010/internal/v1/collections", headers=bearer)
        public.raise_for_status()
        assert not {"personal-library", "social-systems"} & {r["id"] for r in public.json()}
    summary = {}
    for mode in ["keyword", "semantic", "hybrid"]:
        rows = [r for r in results if r["mode_requested"] == mode]
        ok = [r for r in rows if r["status"] == "PASS"]
        summary[mode] = {
            "questions": len(rows),
            "responses": len(ok),
            "hit_at_5": sum(r["hit_at_5"] for r in ok) / len(rows),
            "recall_at_5": sum(r["recall_at_5"] for r in ok) / len(rows),
            "mrr_at_5": sum(r["reciprocal_rank_at_5"] for r in ok) / len(rows),
            "median_seconds": statistics.median(r["seconds"] for r in ok) if ok else None,
            "fallbacks": sum(bool(r.get("fallback")) for r in ok),
        }
    assert settings.embedding_provider == "ollama"
    with session() as db:
        texts = list(
            db.scalars(
                select(Chunk.text)
                .join(Document)
                .join(LibraryBook)
                .where(
                    LibraryBook.owner_id == owner,
                    LibraryBook.approved.is_(True),
                    LibraryBook.active_generation == Document.book_generation,
                    Chunk.revision == Document.active_revision,
                )
                .order_by(Chunk.id)
                .limit(32)
            )
        )
    embedder = provider(settings)
    start = time.monotonic()
    vectors = embedder.embed_documents(texts)
    seconds = time.monotonic() - start
    assert len(vectors) == len(texts) and all(len(v) == 1024 for v in vectors)
    report = {
        "source_questions": len(QUESTIONS),
        "summary": summary,
        "results": results,
        "security": {
            "service_token_alone_denied": True,
            "expired_assertion_denied": True,
            "other_user_evidence_empty": True,
            "other_user_counts_zero": True,
            "private_catalog_requires_assertion": True,
            "shared_scope_excludes_books": True,
            "public_catalog_excludes_private_collections": True,
            "sample_citations_owner_and_active_revision_verified": True,
        },
        "embedding_probe": {
            "passages": len(texts),
            "dimensions": 1024,
            "seconds": round(seconds, 3),
            "passages_per_second": round(len(texts) / seconds, 2),
            "identity": embedder.identity,
            "scope": "Local 32-passage probe under current load, including verification and HTTP overhead; no vectors persisted or dumped",
        },
        "unanswerable_question": "See private backend live acceptance: sealed code unavailable; no guess generated.",
        "limits": "Six explicit gold books, one per category. Not exhaustive relevance judgments, chunk-level recall, answer accuracy or degree equivalence.",
    }
    atomic_json(ROOT / "reports" / "retrieval-evaluation.json", report)
    print(
        json.dumps(
            {
                "summary": summary,
                "security_checks": "PASS",
                "embedding_probe": report["embedding_probe"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
