"""Compatibility entry point for source-bound reviewed metrics.

Historical keyword/locator scoring, synthetic recall denominators and score-only
abstention claims have been removed. No unreviewed candidates are gold labels.
"""

from app.library.quality import reviewed_metrics


def evaluate_passage_and_document(hits, q_item, *, citation_checks=None):
    if citation_checks is None:
        raise ValueError("DATABASE_CITATION_CHECKS_REQUIRED")
    return reviewed_metrics(hits, q_item, citation_checks)


if __name__ == "__main__":
    from scripts.evaluate_verified_quality import main

    main()
