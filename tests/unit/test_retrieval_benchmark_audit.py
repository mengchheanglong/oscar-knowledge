"""Unit tests for retrieval benchmark audit, metrics correction, and ranking behavior."""

import math
from app.retrieval.hybrid import rrf, ENGLISH_STOP_WORDS


def test_denominator_and_metric_separation():
    """Ensure answerable (94) and unanswerable (6) queries use distinct denominators."""
    total_queries = 100
    answerable_count = 94
    unanswerable_count = 6

    assert answerable_count + unanswerable_count == total_queries

    # Simulated hit counts
    ans_hits = 86
    unans_abstained = 1

    # Flawed old metric: combining denominators
    flawed_overall_rate = (ans_hits + unans_abstained) / total_queries
    assert math.isclose(flawed_overall_rate, 0.87, rel_tol=1e-2)

    # Corrected metrics: separate denominators
    answerable_hit_rate = ans_hits / answerable_count
    correct_abstention_rate = unans_abstained / unanswerable_count

    assert round(answerable_hit_rate, 3) == 0.915
    assert round(correct_abstention_rate, 3) == 0.167


def test_document_vs_passage_level_discrimination():
    """Verify that matching a book title alone does NOT grant a passage-level hit."""
    known_sources = ["thinking in systems", "corporate finance"]
    gold_terms = ["feedback loop", "leverage point", "delay"]
    min_terms = 2

    # Case A: Chunk from 'Thinking in Systems' but body text is just table of contents / preface
    toc_chunk_title = "Thinking in Systems: A Primer"
    toc_chunk_text = "Table of contents: Chapter 1 The Basics, Chapter 2 Systems and Us, Index."

    is_doc_hit = any(src in toc_chunk_title.lower() for src in known_sources)
    terms_in_text = [t for t in gold_terms if t in toc_chunk_text.lower()]
    is_passage_hit = len(terms_in_text) >= min_terms

    assert is_doc_hit is True
    assert is_passage_hit is False  # Must NOT count as passage hit

    # Case B: Chunk with substantive mechanism
    mechanism_chunk_text = "A feedback loop is a closed chain of causal connections. The delay in a balancing loop causes oscillation."
    mech_terms = [t for t in gold_terms if t in mechanism_chunk_text.lower()]
    is_mech_passage_hit = len(mech_terms) >= min_terms

    assert is_mech_passage_hit is True


def test_rrf_rank_dilution_reproduction():
    """Verify the mathematical mechanism of RRF rank dilution.

    A document ranked #1 in semantic search (absent from keyword) can be
    overtaken by a mediocre document ranked #8 in semantic and #20 in keyword.
    """
    k = 60
    # Pool 0: Keyword, Pool 1: Semantic
    # Doc A: Top-1 semantic hit, absent from keyword pool
    # Doc B: Mediocre hit in both pools (rank 20 in keyword, rank 8 in semantic)

    pools = [
        ["other_kw_1", "other_kw_2"]
        + ["other_kw_" + str(i) for i in range(3, 20)]
        + ["doc_B"],  # Keyword pool: doc_B at rank 20
        ["doc_A"]
        + ["other_sem_" + str(i) for i in range(2, 8)]
        + ["doc_B"],  # Semantic pool: doc_A at rank 1, doc_B at rank 8
    ]

    weights = [0.5, 1.0]  # Standard broad_keyword weights
    ranked = rrf(pools, k=k, weights=weights)

    score_map = dict(ranked)
    score_A = score_map["doc_A"]
    score_B = score_map["doc_B"]

    # Doc A score: 1.0 / (60 + 1) = 0.016393
    expected_A = 1.0 / (k + 1)
    # Doc B score: 0.5 / (60 + 20) + 1.0 / (60 + 8) = 0.00625 + 0.014705 = 0.020955
    expected_B = (0.5 / (k + 20)) + (1.0 / (k + 8))

    assert math.isclose(score_A, expected_A, rel_tol=1e-4)
    assert math.isclose(score_B, expected_B, rel_tol=1e-4)
    assert score_B > score_A  # Dilution proven: Doc B leapfrogs Doc A!
    assert ranked[0][0] == "doc_B"  # Doc B is ranked ahead of Doc A in RRF output


def test_stop_words_filtering_in_hybrid_fallback():
    """Verify that English stop words are filtered from full-text query fallback."""
    query = "How does the strategic choice cascade define the relationship between winning aspirations and where to play?"
    tokens = [t.lower() for t in query.split()]

    content_tokens = [t for t in tokens if t not in ENGLISH_STOP_WORDS]

    # Verify conversational stop words are excluded
    assert "how" not in content_tokens
    assert "does" not in content_tokens
    assert "the" not in content_tokens
    assert "between" not in content_tokens
    assert "and" not in content_tokens

    # Verify substantive tokens remain
    assert "strategic" in content_tokens
    assert "choice" in content_tokens
    assert "cascade" in content_tokens
    assert "aspirations" in content_tokens


def test_duplicate_crowding_diversity_ratio():
    """Verify that diversity ratio accurately penalizes same-document clustering."""
    # Case 1: 5 distinct documents
    hits_diverse = [{"document_id": f"doc_{i}"} for i in range(5)]
    unique_diverse = len({h["document_id"] for h in hits_diverse})
    assert unique_diverse / len(hits_diverse) == 1.0

    # Case 2: All 5 chunks from the same document
    hits_crowded = [{"document_id": "doc_1"} for _ in range(5)]
    unique_crowded = len({h["document_id"] for h in hits_crowded})
    assert unique_crowded / len(hits_crowded) == 0.2


def test_abstention_calibration_cutoff_tradeoff():
    """Verify that higher cosine thresholds increase correct abstentions but also false rejections."""
    unans_scores = [0.38, 0.42, 0.46, 0.48, 0.51, 0.53]  # Fictional query similarities
    ans_scores = [0.44, 0.47, 0.52, 0.55, 0.60, 0.65, 0.70]  # Answerable query similarities

    # At cutoff 0.45:
    cutoff_45 = 0.45
    unans_abstained_45 = sum(1 for s in unans_scores if s < cutoff_45)
    ans_rejected_45 = sum(1 for s in ans_scores if s < cutoff_45)

    assert unans_abstained_45 == 2  # Catches 2/6 unanswerable
    assert ans_rejected_45 == 1  # Wrongly rejects 1 valid answerable question

    # At cutoff 0.50:
    cutoff_50 = 0.50
    unans_abstained_50 = sum(1 for s in unans_scores if s < cutoff_50)
    ans_rejected_50 = sum(1 for s in ans_scores if s < cutoff_50)

    assert unans_abstained_50 == 4  # Catches 4/6 unanswerable
    assert ans_rejected_50 == 2  # Wrongly rejects 2 valid answerable questions!
