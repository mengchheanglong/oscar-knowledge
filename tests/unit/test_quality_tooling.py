"""Unit tests for content quality audit and educational coverage tooling."""

import re
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.audit_educational_coverage import (
    MAJOR_EDUCATIONAL_METRICS,
    parse_unit_file,
)
from scripts.evaluate_retrieval_quality import BENCHMARK_QUERIES


def test_parse_unit_file_bullet_and_hyphen_handling():
    sample_content = """# Unit 01: Test Quantitative Topic

## Outcomes
Explain and distinguish negative cash flows -5% to -10% variance.

## Assigned source collections
- -source-alpha
- --source-beta
- normal-collection

## Located reading evidence
- -10% margin analysis in section 3.2
- [Chapter 1 Introduction](<test/path/INDEX.md>)
"""
    with TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "unit-01.md"
        tmp_file.write_text(sample_content, encoding="utf-8")

        res = parse_unit_file(tmp_file)
        assert res["title"] == "Unit 01: Test Quantitative Topic"
        assert "negative cash flows -5% to -10% variance" in res["outcomes"]
        # Bullet stripping must strip the leading "- " but preserve internal or leading hyphens in names
        assert "-source-alpha" in res["assigned_sources"]
        assert "--source-beta" in res["assigned_sources"]
        assert "normal-collection" in res["assigned_sources"]
        # Negative sign must not be eaten away
        assert "-10% margin analysis in section 3.2" in res["located_evidence"]
        assert "[Chapter 1 Introduction](<test/path/INDEX.md>)" in res["located_evidence"]


def test_major_educational_metrics_22_distinct_majors():
    assert len(MAJOR_EDUCATIONAL_METRICS) == 22

    # Verify marketing vs marketing-operations separation
    marketing = MAJOR_EDUCATIONAL_METRICS["marketing"]
    marketing_ops = MAJOR_EDUCATIONAL_METRICS["marketing-operations"]

    assert "Markstrat" in marketing["gap"]
    assert "Marketing mix optimization" in marketing["worked_examples"]

    assert "ERP systems (SAP/Oracle)" in marketing_ops["gap"]
    assert "EOQ" in marketing_ops["worked_examples"]
    assert "Markstrat" not in marketing_ops["gap"]

    # Verify quantitative finance
    qfin = MAJOR_EDUCATIONAL_METRICS["quantitative-finance"]
    assert "Black-Scholes PDE" in qfin["worked_examples"]
    assert "High-frequency order book feeds" in qfin["gap"]

    # Verify statistics and data science
    stats_ds = MAJOR_EDUCATIONAL_METRICS["statistics-data-science"]
    assert "K-fold cross-validation" in stats_ds["worked_examples"]

    # Verify individualized major is marked NEEDS_REVIEW
    indiv = MAJOR_EDUCATIONAL_METRICS["individualized"]
    assert indiv["status"] == "NEEDS_REVIEW"

    # All other 21 majors must be VERIFIED
    verified_count = sum(1 for m in MAJOR_EDUCATIONAL_METRICS.values() if m["status"] == "VERIFIED")
    assert verified_count == 21


def test_summary_and_study_guide_regex_accuracy():
    summary_titles = [
        "Summary of The Lean Startup",
        "Summaries of Great Business Ideas",
        "Thinking, Fast and Slow (Blinkist Summary)",
        "Shortform: Principles by Ray Dalio",
        "Instaread Summary of Good to Great",
    ]
    non_summary_titles = [
        "Central Banking, Banknotes and Monetary Policy",
        "Corporate Finance: The Issuance of Notes and Bonds",
        "Macroeconomics Lecture 04: Banknotes and Currency Circulation",
        "Accounting for Long-Term Notes Payable",
    ]
    study_guide_titles = [
        "Financial Statement Analysis Study Guide",
        "Economics for Business Study Guide 2026",
    ]

    summary_pattern = r"\bsummar(y|ies)\b"

    for t in summary_titles:
        tl = t.lower()
        is_summary = (
            bool(re.search(summary_pattern, tl))
            or "blinkist" in tl
            or "shortform" in tl
            or "instaread" in tl
        )
        assert is_summary, f"Expected {t} to be detected as summary"

    for t in non_summary_titles:
        tl = t.lower()
        is_summary = (
            bool(re.search(summary_pattern, tl))
            or "blinkist" in tl
            or "shortform" in tl
            or "instaread" in tl
        )
        assert not is_summary, f"Expected {t} NOT to be detected as summary"

    for t in study_guide_titles:
        tl = t.lower()
        is_study_guide = bool(re.search(r"\bstudy\s+guide\b", tl))
        assert is_study_guide, f"Expected {t} to be detected as study guide"


def test_benchmark_queries_integrity():
    assert len(BENCHMARK_QUERIES) == 37

    categories = {q["category"] for q in BENCHMARK_QUERIES}
    assert categories == {
        "mba_major",
        "general_library",
        "ocr_math_table",
        "attribution",
        "unanswerable",
    }

    # Verify counts per category
    cat_counts = {}
    for q in BENCHMARK_QUERIES:
        cat_counts[q["category"]] = cat_counts.get(q["category"], 0) + 1

    assert cat_counts["mba_major"] == 22
    assert cat_counts["general_library"] == 7
    assert cat_counts["ocr_math_table"] == 3
    assert cat_counts["attribution"] == 3
    assert cat_counts["unanswerable"] == 2

    # Verify fields
    for q in BENCHMARK_QUERIES:
        assert q["id"], "Query ID cannot be empty"
        assert len(q["query"]) > 10, "Query string too short"
        assert len(q["expected_collections"]) > 0, "Expected collections missing"
        assert len(q["gold_keywords"]) > 0, "Gold keywords missing"
        assert isinstance(q["unanswerable"], bool)
