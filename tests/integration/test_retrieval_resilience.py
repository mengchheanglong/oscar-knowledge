import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.api.schemas import RetrievalRequest
from app.config import Settings
from app.db.models import ChunkEmbedding
from app.embeddings.base import EmbeddingError
from app.retrieval import hybrid
from tests.integration.test_topic_graph import passage


def test_query_timeout_rolls_back_and_restores_statement_budget(db):
    previous = db.scalar(select(text("current_setting('statement_timeout')")))
    assert hybrid.ranked_query(db, select(text("pg_sleep(0.05)")), 10) is None
    assert db.scalar(select(text("1"))) == 1
    assert db.scalar(select(text("current_setting('statement_timeout')"))) == previous


@pytest.mark.parametrize("failed", ["keyword", "vector", "both"])
@pytest.mark.parametrize("focused", [False, True])
def test_hybrid_retains_healthy_channel_without_leaking_private_passages(
    db, monkeypatch, failed, focused
):
    seed, _ = passage(
        db, "Permitted pricing", "Customer value and subscription pricing require evidence. " * 6
    )
    hidden, _ = passage(
        db, "Private pricing", "Customer value and subscription pricing. " * 8, owner=uuid.uuid4()
    )
    vector = [1.0] + [0.0] * 1023
    for chunk in [seed, hidden]:
        db.add(
            ChunkEmbedding(
                chunk_id=chunk.id, identity="fixture-1024", dimensions=1024, embedding_1024=vector
            )
        )
    db.commit()
    monkeypatch.setattr(
        hybrid,
        "provider",
        lambda settings: SimpleNamespace(
            embed_query=lambda query: vector,
            identity="fixture-1024",
            dimensions=1024,
            legacy_identity=None,
        ),
    )
    original = hybrid.ranked_query

    def controlled(db, statement, budget):
        is_vector = "<=>" in str(statement)
        if failed == "both" or is_vector == (failed == "vector"):
            return None
        return original(db, statement, budget)

    monkeypatch.setattr(hybrid, "ranked_query", controlled)
    request = RetrievalRequest(
        query='According to "Permitted pricing", explain customer value and subscription pricing.'
        if focused
        else "customer value subscription pricing",
        collection_ids=["mba-business", "personal-library"],
        graph_expand=False,
    )
    settings = Settings(graph_enabled=False)
    if failed == "both":
        with pytest.raises(EmbeddingError):
            hybrid.retrieve(db, request, settings, subject=str(uuid.uuid4()))
        return
    result = hybrid.retrieve(db, request, settings, subject=str(uuid.uuid4()))
    assert result.results and result.results[0].chunk_id == seed.id
    assert all(i.chunk_id != hidden.id for i in result.results)
    assert result.retrieval_mode_used == ("semantic" if failed == "keyword" else "keyword")
    assert result.fallback_reason == (
        "KEYWORD_RETRIEVAL_UNAVAILABLE" if failed == "keyword" else "VECTOR_RETRIEVAL_UNAVAILABLE"
    )


def test_long_instruction_heavy_question_keeps_concept_passages(db):
    seed, _ = passage(
        db,
        "Pricing principles",
        "Willingness to pay informs subscription pricing. Customer value must be tested. " * 8,
    )
    request = RetrievalRequest(
        query="For a merchant, how can we connect willingness to pay, subscription pricing and customer value? Cite the original source passages and explain your synthesis across the permitted library. "
        * 5,
        mode="keyword",
        graph_expand=False,
    )
    result = hybrid.retrieve(db, request, Settings())
    assert seed.id in {i.chunk_id for i in result.results}
