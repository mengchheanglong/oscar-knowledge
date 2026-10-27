# Focused source retrieval — 2026-10-27

When a query names a title found among eligible initial candidates, retrieval
can search the requested concept within that source. Matching removes the
title's words from the lexical topic so repeated book headings do not overwhelm
the definition. Book identity spans document fragments; non-book sources stay
within matched documents. No global private-title discovery is introduced.

The extra bounded pool tries conjunctive concept terms, then disjunctive terms
if necessary. Local term rarity and phrase coverage order candidates. Up to two
leading passages per source (at most six, within requested top K) precede the
remaining weighted RRF list. Existing per-book diversity limits remain. Scores
describe this ordering; they are not probabilities or calibrated confidence.
Every extra query reuses current collection, filter, revision, generation,
approval, visibility, private-reader and chunk-exclusion conditions.

No source content, vectors, IDs, provenance or revisions are rewritten. The
fifteen existing exclusions remain effective in the local run. Verification:
153 tests passed, one skipped; Ruff and mypy passed. New integration cases cover
cross-fragment definition recovery behind a saturated introductory pool,
unapproved and stale content, exact exclusion and private-reader isolation.

Actual main-app testing recovered the exposed buyer and pivot-point passages.
The eight fresh app questions yielded four substantive answers, two partial
answers and two appropriate unsupported-request refusals. Three of the six
answerable questions included a preselected gold passage, while one additional
answer used relevant alternative passages. This is neither retrieval precision
nor corpus-wide recall. The hiring qualification and systems definition were
missed. English lexical heuristics, first-pool title discovery and bounded
candidate ordering still limit recovery, particularly for multi-part questions.

Private receipts and frozen questions are in
`D:\AI\OSCAR\Knowledge\Catalog\reports\retrieval-grounding\2026-10-27`.
Main OSCAR performs the additional semantic answer review; this service remains
an evidence retriever. The overall semantic quality gate is not passed.
