"""Passage-level evaluation against source-reviewed, hash-pinned page judgments."""

import statistics
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.api.schemas import Filters, RetrievalRequest
from app.db.models import Chunk, Collection, Document
from app.retrieval.hybrid import retrieve


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldSource(StrictModel):
    source_key: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class GoldPassage(StrictModel):
    course: str
    page: int = Field(ge=1)
    anchor: str = Field(min_length=3, max_length=100)
    alternative_pages: list[int] = Field(default_factory=list, max_length=20)


class GoldQuestion(StrictModel):
    id: str
    query: str = Field(min_length=1, max_length=4000)
    gold: list[GoldPassage] = Field(max_length=10)


class PassageDataset(StrictModel):
    name: str
    review_notes: str
    collection: str
    sources: dict[str, GoldSource]
    questions: list[GoldQuestion] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_labels(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("DUPLICATE_QUESTION_ID")
        for question in self.questions:
            for gold in question.gold:
                if gold.course not in self.sources:
                    raise ValueError("UNKNOWN_GOLD_SOURCE")
        return self


def normalize(text):
    return " ".join(text.casefold().split())


def rank_metrics(found, targets):
    """A target can match several chunks on the same verified page; count it once."""
    if not targets:
        return None
    union = set().union(*targets)
    return {
        "hit": int(bool(set(found) & union)),
        "recall": sum(bool(set(found) & target) for target in targets) / len(targets),
        "rr": next((1 / rank for rank, key in enumerate(found, 1) if key in union), 0),
    }


def evaluate_passages(
    db, dataset: PassageDataset, settings, mode: Literal["keyword", "semantic", "hybrid"]
):
    if dataset.collection not in settings.allowed_collections:
        raise ValueError("COLLECTION_NOT_ALLOWED")
    documents, chunks = {}, {}
    for course, source in dataset.sources.items():
        doc = db.scalar(
            select(Document)
            .join(Collection)
            .where(
                Collection.slug == dataset.collection,
                Document.canonical_key == source.source_key,
                Document.approved.is_(True),
                Document.status != "DELETED",
                Document.active_revision > 0,
            )
        )
        if not doc or doc.content_sha256 != source.sha256 or doc.course_code != course:
            raise ValueError("GOLD_SOURCE_MISSING_OR_CHANGED")
        documents[course] = doc
        chunks.update(
            {
                c.id: c
                for c in db.scalars(
                    select(Chunk).where(
                        Chunk.document_id == doc.id, Chunk.revision == doc.active_revision
                    )
                )
            }
        )
    rows, ranked, latencies = [], [], []
    locator_checked = locator_correct = 0
    for question in dataset.questions:
        targets = []
        for gold in question.gold:
            ids = {
                c.id
                for c in chunks.values()
                if c.document_id == documents[gold.course].id
                and c.page_start is not None
                and any(
                    c.page_start <= page <= (c.page_end or c.page_start)
                    for page in [gold.page, *gold.alternative_pages]
                )
                and normalize(gold.anchor) in normalize(c.text)
            }
            if not ids:
                raise ValueError("GOLD_PASSAGE_NOT_VERIFIED")
            targets.append(ids)
        start = time.perf_counter()
        response = retrieve(
            db,
            RetrievalRequest(
                query=question.query,
                collection_ids=[dataset.collection],
                top_k=5,
                mode=mode,
                filters=Filters(document_ids=[doc.id for doc in documents.values()]),
            ),
            settings,
        )
        latency = time.perf_counter() - start
        latencies.append(latency)
        found = [r.chunk_id for r in response.results]
        metrics = rank_metrics(found, targets)
        if metrics:
            ranked.append(metrics)
        results = []
        for result in response.results:
            chunk = chunks[result.chunk_id]
            doc = next(d for d in documents.values() if d.id == chunk.document_id)
            correct = (
                result.page_start == chunk.page_start
                and result.page_end == chunk.page_end
                and result.source_url == doc.source_url
                and result.revision == doc.active_revision
                and result.locator is not None
                and f"Page {chunk.page_start}" in result.locator
            )
            locator_checked += 1
            locator_correct += int(correct)
            results.append(
                {
                    "chunk_id": str(result.chunk_id),
                    "course": result.course_code,
                    "page": result.page_start,
                    "rank": result.rank,
                    "score": result.score,
                    "locator_valid": correct,
                    "matches_gold": any(result.chunk_id in target for target in targets),
                }
            )
        rows.append(
            {
                "id": question.id,
                "query": question.query,
                "answerable": bool(targets),
                "metrics": metrics,
                "seconds": latency,
                "actual_mode": response.retrieval_mode_used,
                "fallback_reason": response.fallback_reason,
                "results": results,
            }
        )
    negatives = [r for r in rows if not r["answerable"]]
    return {
        "dataset": dataset.name,
        "requested_mode": mode,
        "top_k": 5,
        "questions": len(rows),
        "answerable_questions": len(ranked),
        "unanswerable_questions": len(negatives),
        "gold_passage_judgments": sum(len(q.gold) for q in dataset.questions),
        "Hit@5": statistics.mean(r["hit"] for r in ranked) if ranked else None,
        "Recall@5": statistics.mean(r["recall"] for r in ranked) if ranked else None,
        "MRR@5": statistics.mean(r["rr"] for r in ranked) if ranked else None,
        "mean_seconds": statistics.mean(latencies),
        "p95_seconds": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
        "citation_locator_accuracy": locator_correct / locator_checked if locator_checked else None,
        "unanswerable_false_positive_rate": sum(bool(r["results"]) for r in negatives)
        / len(negatives)
        if negatives
        else None,
        "unanswerable_correct_rejection_rate": sum(not r["results"] for r in negatives)
        / len(negatives)
        if negatives
        else None,
        "fallback_count": sum(r["fallback_reason"] is not None for r in rows),
        "precision_note": "Only gold passages and unanswerable questions are judged; other returned passages are unjudged, not automatically false positives.",
        "rows": rows,
    }
