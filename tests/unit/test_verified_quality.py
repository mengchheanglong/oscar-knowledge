import hashlib

import pytest

from app.library.quality import classify_representation, reviewed_metrics
from scripts.apply_verified_repairs import corrected_note
from scripts.evaluate_rigorous_audit import evaluate_passage_and_document


def test_textbook_chapter_summary_is_not_a_commercial_book_summary():
    assert (
        classify_representation({"title": "1.10 Summary – Macroeconomics", "format": "html"})
        == "CHAPTER_SUMMARY_SECTION"
    )
    assert (
        classify_representation({"title": "Summary statistics", "format": "md"}) == "UNCLASSIFIED"
    )
    assert classify_representation({"title": "Course summary", "format": "pdf"}) == "COURSE_SUMMARY"
    assert (
        classify_representation(
            {"title": "Summary of Getting to Yes", "filename": "Instaread.pdf", "format": "pdf"}
        )
        == "PUBLISHER_SUMMARY"
    )


def test_field_repair_preserves_user_edits_instead_of_restoring_entire_catalog():
    assert corrected_note("bad automated note", "bad automated note", None, None) is None
    assert (
        corrected_note("correct summary note", "bad automated note", None, "correct summary note")
        == "correct summary note"
    )
    with pytest.raises(ValueError, match="QUALITY_METADATA_CONFLICT"):
        corrected_note("user correction", "bad automated note", None, None)


def test_unreviewed_keywords_and_fake_ids_never_count_as_verified_support():
    hits = [
        {
            "chunk_id": "fake",
            "document_id": "fake",
            "locator": "joint conditional probability",
            "text": "unrelated",
        }
    ]
    with pytest.raises(ValueError, match="DATABASE_CITATION_CHECKS_REQUIRED"):
        evaluate_passage_and_document(hits, {"gold_evidence": {"gold_terms": ["joint"]}})
    with pytest.raises(ValueError, match="REVIEWED_GOLD_REQUIRED"):
        reviewed_metrics(hits, {"review_status": "UNJUDGED"}, [False])


def test_pooled_metrics_use_all_judged_relevant_passages_and_ignore_duplicates():
    def label(grade):
        return {
            "grade": grade,
            "text_sha256": hashlib.sha256(b"body").hexdigest(),
            "document_id": "doc",
            "revision": 1,
        }

    q = {"review_status": "REVIEWED", "reviewed_qrels": {"a": label(1), "b": label(2)}}
    hit = {"chunk_id": "a", "document_id": "doc", "revision": 1, "text": "body"}
    result = reviewed_metrics([hit, hit], q, [True, True])
    assert result["pooled_recall_at_5"] == 0.5
    assert result["passage_grades"] == [1, 0]
    assert 0 < result["pooled_ndcg_at_5"] < 1
    assert not reviewed_metrics([hit], q, [False])["passage_hit_at_5"]
    assert not reviewed_metrics([{**hit, "text": "changed body"}], q, [True])["passage_hit_at_5"]
    with pytest.raises(ValueError, match="REVIEWED_GRADE_INVALID"):
        reviewed_metrics([hit], {**q, "reviewed_qrels": {"a": label(100)}}, [True])


def test_unit_structure_does_not_certify_substantive_educational_coverage(tmp_path, monkeypatch):
    import scripts.audit_educational_coverage as audit

    track = tmp_path / "tracks/accounting/units"
    track.mkdir(parents=True)
    (track / "unit-01.md").write_text(
        "# Unit 01: Missing actual sources\n\n## Outcomes\nCompute cash flows\n", encoding="utf-8"
    )
    monkeypatch.setattr(audit, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(audit, "TRACKS_DIR", tmp_path / "tracks")
    rows = audit.audit_mba_coverage()
    assert len(rows) == 1
    assert rows[0]["quality_status"] == "NEEDS_REVIEW"
    assert "not independently verified" in rows[0]["assessment_status"]
