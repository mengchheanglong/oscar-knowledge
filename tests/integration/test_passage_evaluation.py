import pymupdf
import pytest

from app.config import Settings
from app.db.models import Document
from app.evaluation import PassageDataset, evaluate_passages
from app.ingestion.pipeline import enqueue, process_job

pytestmark = pytest.mark.integration


def test_real_page_gold_metrics_locator_checks_and_changed_or_withdrawn_source(db, tmp_path):
    path = tmp_path / "gold.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Subscription pricing uses customer value.")
        pdf.save(path)
    job = enqueue(db, path, "mba-business", approved=True, canonical_key="gold", course_code="GOLD")
    assert process_job(db, job.id, Settings()) == "INDEXED"
    doc = db.get(Document, job.document_id)
    dataset = PassageDataset.model_validate(
        {
            "name": "original test",
            "review_notes": "Original authored source, page checked",
            "collection": "mba-business",
            "sources": {"GOLD": {"source_key": "gold", "sha256": doc.content_sha256}},
            "questions": [
                {
                    "id": "answerable",
                    "query": "subscription pricing",
                    "gold": [{"course": "GOLD", "page": 1, "anchor": "customer value"}],
                },
                {"id": "unanswerable", "query": "zzzzxylophonexxxx", "gold": []},
            ],
        }
    )
    report = evaluate_passages(db, dataset, Settings(), "keyword")
    assert report["Hit@5"] == report["Recall@5"] == report["MRR@5"] == 1
    assert report["citation_locator_accuracy"] == 1
    assert report["unanswerable_false_positive_rate"] == 0
    dataset.questions[0].gold[0].page = 2
    with pytest.raises(ValueError, match="GOLD_PASSAGE_NOT_VERIFIED"):
        evaluate_passages(db, dataset, Settings(), "keyword")
    dataset.questions[0].gold[0].page = 1
    dataset.sources["GOLD"].sha256 = "0" * 64
    with pytest.raises(ValueError, match="GOLD_SOURCE_MISSING_OR_CHANGED"):
        evaluate_passages(db, dataset, Settings(), "keyword")
    dataset.sources["GOLD"].sha256 = doc.content_sha256
    doc.approved = False
    db.commit()
    with pytest.raises(ValueError, match="GOLD_SOURCE_MISSING_OR_CHANGED"):
        evaluate_passages(db, dataset, Settings(), "keyword")
