"""Compatibility entry point. Candidate matches cannot certify semantic ground truth.

Use --broad for citation-integrity checks over the historical 100 questions.
Only the separately reviewed frozen pool receives relevance metrics.
Historical heuristic reports remain superseded and are not regenerated.
"""

from scripts.evaluate_verified_quality import main

if __name__ == "__main__":
    main()
