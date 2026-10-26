"""Evidence-bound quality checks. Heuristic candidates are never gold labels."""

import hashlib
import math
import uuid

from sqlalchemy import select

from app.db.models import Chunk, Collection, Document, LibraryBook


CURRENT_EVIDENCE_SQL = """
d.status != 'DELETED' AND d.approved AND c.revision = d.active_revision
AND c.collection_id = d.collection_id
AND ((d.book_id IS NULL AND col.visibility = 'CURATED_SHARED') OR
 (b.approved AND b.status IN ('INDEXED', 'PARTIALLY_INDEXED')
  AND b.active_generation = d.book_generation AND b.collection_id = d.collection_id
  AND b.visibility = col.visibility))
"""


def classify_representation(resource):
    """Conservative type hints, not an assertion of source fidelity or completeness."""
    import re

    title = resource.get("title", "").lower()
    if resource.get("format") == "pdf" and any(
        name in title + " " + resource.get("filename", "").lower()
        for name in ["instaread", "blinkist", "shortform", "cliffsnotes", "sparknotes"]
    ):
        return "PUBLISHER_SUMMARY"
    if resource.get("format") == "pdf" and re.search(r"\bstudy\s+guide\b", title):
        return "COURSE_STUDY_GUIDE"
    if resource.get("format") == "pdf" and "course summary" in title:
        return "COURSE_SUMMARY"
    if resource.get("format") in {"html", "htm"} and re.match(r"^\d+(?:\.\d+)+\s+summary\b", title):
        return "CHAPTER_SUMMARY_SECTION"
    return "UNCLASSIFIED"


def validate_citations(db, hits, *, subject, collections):
    """Check actual current identity, scope, revision, text and physical page bounds."""
    checks = []
    for hit in hits:
        try:
            identifier = uuid.UUID(str(hit.get("chunk_id")))
        except (ValueError, TypeError, AttributeError):
            checks.append(False)
            continue
        row = db.execute(
            select(Chunk, Document, Collection, LibraryBook)
            .join(Document, Chunk.document_id == Document.id)
            .join(Collection, Document.collection_id == Collection.id)
            .outerjoin(LibraryBook, Document.book_id == LibraryBook.id)
            .where(Chunk.id == identifier)
        ).first()
        if not row:
            checks.append(False)
            continue
        chunk, doc, col, book = row
        current = bool(
            col.slug in collections
            and hit.get("collection_id") == col.slug
            and str(doc.id) == str(hit.get("document_id"))
            and doc.approved
            and doc.status != "DELETED"
            and chunk.collection_id == doc.collection_id
            and chunk.revision == doc.active_revision == hit.get("revision")
            and hit.get("page_start") == chunk.page_start
            and hit.get("page_end") == chunk.page_end
            and hit.get("text") == chunk.text
            and hit.get("title") == doc.title
        )
        if doc.book_id:
            current = current and bool(
                book
                and str(book.id) == str(hit.get("book_id"))
                and book.approved
                and book.status in {"INDEXED", "PARTIALLY_INDEXED"}
                and book.active_generation == doc.book_generation
                and book.collection_id == doc.collection_id
                and book.visibility == col.visibility
                and (
                    (book.visibility == "PRIVATE" and str(book.owner_id) == subject)
                    or book.visibility == "CURATED_SHARED"
                )
            )
        else:
            current = current and col.visibility == "CURATED_SHARED" and not hit.get("book_id")
        checks.append(bool(current))
    return checks


def reviewed_metrics(hits, question, citation_checks):
    """Metrics over frozen, reviewed chunk IDs; denominator is the judged pool.

    Unjudged results get no relevance credit, but are counted explicitly. This
    is pooled recall, not an estimate of all relevant passages in the library.
    """
    gold = question.get("reviewed_qrels")
    if not gold or question.get("review_status") != "REVIEWED":
        raise ValueError("REVIEWED_GOLD_REQUIRED")
    if any(
        type(label.get("grade")) is not int or not 0 <= label["grade"] <= 2
        for label in gold.values()
    ):
        raise ValueError("REVIEWED_GRADE_INVALID")
    if len(citation_checks) != len(hits):
        raise ValueError("CITATION_CHECK_COUNT")
    positive = {key: value for key, value in gold.items() if value["grade"] > 0}
    if not positive:
        raise ValueError("POSITIVE_REVIEWED_GOLD_REQUIRED")
    grades, seen = [], set()
    unjudged = 0
    for hit, valid in zip(hits, citation_checks, strict=True):
        identifier = str(hit.get("chunk_id"))
        label = gold.get(identifier)
        if not label:
            unjudged += 1
        bound = bool(
            valid
            and label
            and label["text_sha256"] == hashlib.sha256(hit["text"].encode()).hexdigest()
            and label["document_id"] == str(hit["document_id"])
            and label["revision"] == hit["revision"]
        )
        grades.append(label["grade"] if bound and identifier not in seen else 0)
        seen.add(identifier)
    ideal = sorted((label["grade"] for label in positive.values()), reverse=True)[:5]
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:5]))
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    first = next((i for i, g in enumerate(grades[:5], 1) if g), None)
    return {
        "passage_hit_at_1": bool(grades and grades[0]),
        "passage_hit_at_5": any(grades[:5]),
        "mrr_at_5": 1 / first if first else 0,
        "pooled_recall_at_5": sum(bool(g) for g in grades[:5]) / len(positive),
        "pooled_ndcg_at_5": dcg / idcg if idcg else 0,
        "unjudged_results": unjudged,
        "citation_checks": citation_checks,
        "passage_grades": grades[:5],
    }
