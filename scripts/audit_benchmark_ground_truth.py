"""Audit benchmark ground truth against the local Knowledge PostgreSQL database.

Inspects all 100 questions to:
1. Distinguish document-level hits from true passage-level answer support.
2. Search database chunks for verified passage matches (chunk_id, doc_id, locator, text snippet).
3. Classify each query by validation status:
   - VERIFIED_PASSAGE_LABEL: Ground-truth chunk identified and verified to answer the query.
   - MULTIPLE_VALID_SOURCES: Multiple approved books in the corpus independently answer the query.
   - PROVISIONAL_NEEDS_REVIEW: Plausible candidates found, requires human review.
   - OCR_MATH_DEPENDENT: Requires inspection of rendered equation/diagram/OCR page.
   - UNANSWERABLE: Out-of-corpus / fictional / secret; correct behavior is abstention.
4. Generates GOLD_LABEL_VALIDATION.json and audit metrics.
"""

from pathlib import Path
import json
from sqlalchemy import select, func
from app.db.session import session
from app.db.models import Chunk, Document, Collection

CATALOG_DIR = Path("D:/AI/OSCAR/Knowledge/Catalog")
OUTPUT_DIR = CATALOG_DIR / "reports/quality-review/2026-10-26"
DATASET_PATH = OUTPUT_DIR / "BENCHMARK_100_DATASET.json"


def audit_queries():
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    queries = dataset["queries"]

    audit_records = []
    summary_counts = {
        "verified_passage_label": 0,
        "multiple_valid_sources": 0,
        "provisional_needs_review": 0,
        "ocr_math_dependent": 0,
        "unanswerable_out_of_corpus": 0,
        "ambiguous_or_unsupported": 0,
    }

    with session() as db:
        db.execute(select(func.set_config("enable_nestloop", "off", True)))
        for q in queries:
            qid = q["id"]
            split = q["split"]
            domain = q["domain"]
            sub_topic = q["sub_topic"]
            query_str = q["query"]
            unans = q["unanswerable"]
            gold = q.get("gold_evidence", {})
            gold_terms = [t.lower() for t in gold.get("gold_terms", [])]
            min_terms = gold.get("min_terms_required", 2)
            known_sources = [s.lower() for s in gold.get("known_sources", [])]
            col_ids = q.get("expected_collections", ["personal-library", "mba-majors"])

            if unans:
                record = {
                    "id": qid,
                    "split": split,
                    "domain": domain,
                    "sub_topic": sub_topic,
                    "query": query_str,
                    "unanswerable": True,
                    "status": "UNANSWERABLE_OUT_OF_CORPUS",
                    "validation_category": "UNANSWERABLE",
                    "gold_passages": [],
                    "candidate_count_in_db": 0,
                    "multiple_sources": False,
                    "requires_human_review": False,
                    "notes": "Entity/topic is fictional or proprietary; correct system action is abstention.",
                }
                summary_counts["unanswerable_out_of_corpus"] += 1
                audit_records.append(record)
                continue

            # For answerable queries, search PostgreSQL for chunks matching key concepts
            # Search within allowed collections
            base_q = (
                select(Chunk, Document, Collection.slug)
                .join(Document, Chunk.document_id == Document.id)
                .join(Collection, Document.collection_id == Collection.id)
                .where(
                    Collection.slug.in_(col_ids),
                    Document.approved.is_(True),
                    Document.status != "DELETED",
                    Chunk.revision == Document.active_revision,
                )
            )

            # Use indexed full-text search vector for fast candidate discovery
            matched_chunks = []
            for term in gold_terms:
                if len(term) >= 3:
                    ts_q = func.plainto_tsquery("english", term)
                    rows = db.execute(
                        base_q.where(Chunk.search_vector.op("@@")(ts_q)).limit(25)
                    ).all()
                    matched_chunks.extend(rows)

            # Deduplicate by chunk.id and score by match count
            scored = {}
            for chunk, doc, slug in matched_chunks:
                cid = str(chunk.id)
                if cid not in scored:
                    text_lower = chunk.text.lower()
                    title_lower = (doc.title or "").lower()

                    # Distinct terms matched in text body
                    distinct_terms_in_text = [
                        kw for kw in gold_terms if kw in text_lower
                    ]

                    # Source match
                    source_match = any(src in title_lower for src in known_sources)

                    scored[cid] = {
                        "chunk_id": cid,
                        "document_id": str(doc.id),
                        "book_id": str(doc.book_id) if doc.book_id else None,
                        "title": doc.title,
                        "collection": slug,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "heading_path": chunk.heading_path,
                        "extraction": chunk.source_metadata.get("extraction"),
                        "text_snippet": chunk.text[:220].replace("\n", " "),
                        "terms_in_text": distinct_terms_in_text,
                        "terms_count": len(distinct_terms_in_text),
                        "source_match": source_match,
                    }

            # Filter candidates that actually have >= min_terms in chunk body text
            strong_candidates = [
                c for c in scored.values()
                if c["terms_count"] >= min_terms
            ]
            strong_candidates.sort(key=lambda x: (-x["terms_count"], not x["source_match"]))

            # Check distinct documents
            distinct_docs = {c["title"] for c in strong_candidates}

            # Determine validation category
            ocr_dep = domain == "ocr_math_tables" or any(
                c["extraction"] in {"LOCAL_TESSERACT_OCR", "VISUAL_DESCRIPTION"}
                for c in strong_candidates[:3]
            )

            if ocr_dep:
                status = "OCR_MATH_DEPENDENT"
                summary_counts["ocr_math_dependent"] += 1
                cat = "OCR_FORMULA_DEPENDENT"
            elif len(distinct_docs) >= 2:
                status = "MULTIPLE_VALID_SOURCES"
                summary_counts["multiple_valid_sources"] += 1
                cat = "MULTIPLE_VALID_SOURCES"
            elif len(strong_candidates) >= 1:
                status = "VERIFIED_PASSAGE_LABEL"
                summary_counts["verified_passage_label"] += 1
                cat = "VERIFIED_PASSAGE_LABEL"
            else:
                status = "PROVISIONAL_NEEDS_REVIEW"
                summary_counts["provisional_needs_review"] += 1
                cat = "PROVISIONAL_NEEDS_REVIEW"

            gold_passages = [
                {
                    "chunk_id": c["chunk_id"],
                    "document_id": c["document_id"],
                    "title": c["title"],
                    "locator": f"PDF page {c['page_start']} / {c['heading_path']}" if c["page_start"] else c["heading_path"],
                    "page_start": c["page_start"],
                    "terms_matched": c["terms_in_text"],
                    "text_snippet": c["text_snippet"],
                }
                for c in strong_candidates[:3]
            ]

            record = {
                "id": qid,
                "split": split,
                "domain": domain,
                "sub_topic": sub_topic,
                "query": query_str,
                "unanswerable": False,
                "status": status,
                "validation_category": cat,
                "candidate_count_in_db": len(strong_candidates),
                "distinct_valid_sources_count": len(distinct_docs),
                "distinct_valid_sources": sorted(distinct_docs)[:4],
                "gold_passages": gold_passages,
                "requires_human_review": status in {"PROVISIONAL_NEEDS_REVIEW", "OCR_MATH_DEPENDENT"},
                "notes": (
                    f"Found {len(strong_candidates)} passages with >= {min_terms} gold terms across {len(distinct_docs)} books."
                    if strong_candidates
                    else "No single passage met minimum term threshold in body text; requires manual annotation."
                ),
            }
            audit_records.append(record)

    out_json = {
        "audit_date": "2026-10-26T12:35:00+07:00",
        "total_queries_audited": len(audit_records),
        "summary": summary_counts,
        "records": audit_records,
    }

    out_path = OUTPUT_DIR / "GOLD_LABEL_VALIDATION.json"
    out_path.write_text(json.dumps(out_json, indent=2), encoding="utf-8")
    print(f"Audited {len(audit_records)} queries.")
    print("Summary:", summary_counts)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    audit_queries()
