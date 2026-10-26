# Content-quality tooling remediation — 2026-10-26

The independent review found unsupported commercial-summary labels, catalog-only
warnings, historical generations in active scans and heuristic retrieval scores
reported as grounding accuracy. These defects have been corrected. This does
not turn automated screening into a manual review of the whole library.

## Data changes

The source-bound repair reconsiders the 156 historical manifest entries and
restores only the erroneous `metadata.coverage_note` fields. It does not restore
an old catalog over newer grants or edits. Concurrent field edits cause a
conflict instead of being overwritten. Five original PDF first pages were
rendered and visually inspected: one Instaread summary, one MIT course summary
and three MIT quiz guides. Chapter-summary HTML and miscellaneous Markdown/CSV
resources are no longer labeled commercial abridgments merely by keyword.

The active private Instaread book was staged in a new preparation revision and
activated through existing ingestion. Live citations now return its summary
notice. Shared MBA documents remain unchanged; course-guide notices in the
catalog do not imply a change to those shared citations. Old cache files and
generations remain recoverable. Structured-text preparation now also preserves
explicit source notices, with an integration test of the returned citation.

Repreparing the 31-page summary accounts for two additional OCR attempts. Current
catalog coverage records 1,810 OCR-attempt pages rather than the prior 1,808;
this is not a claim that every attempt produced text or was visually verified.
Current original inventory, active references, chunks and vectors remain the
same: 672 PDFs, 198,758 pages; 1,040 private searchable references and 261,212
active private chunks/vector rows. Eighteen other references are reviewed non-text.

## Corrected checks

- SQL screening requires current book generation, approval, document revision,
  collection consistency and visibility. Historical generations are separate.
- OCR outputs are heuristic flags. Existing visual classifications are checked
  structurally; they are not counted as a new independent visual inspection.
- The 176 MBA units and 43 Social Systems readings retain their structural
  coverage matrices, but receive NEEDS_REVIEW for substantive educational
  quality unless independent source-level review evidence exists.
- Historical benchmark commands delegate to `evaluate_verified_quality.py`.
  Keyword/locator matching can no longer create gold labels or an accuracy claim.
- Real citation validation checks actual chunk/document identity, current
  generation/revision, owner, collection, approval, exact text, title and physical
  page bounds. Fabricated IDs and wrong-owner or old-generation evidence fail.
- Relevance metrics require frozen reviewed chunk IDs, text hashes and revisions.
  Pooled recall uses all positive reviewed labels; pooled nDCG uses their global
  ideal ranking. Unjudged results are reported explicitly. Seven previously used
  questions form a small regression pool, not a held-out accuracy benchmark.
- The historical 100 questions can be checked separately for citation integrity.
  No score threshold is reported as proof of generated-answer abstention.
- The hybrid API score description now includes the existing capped metadata
  overlap bonus; the ranking algorithm/model itself was not retuned here.

## Operation

Run from the existing Knowledge `.venv`:

```powershell
# Preview only; requires the private historical manifest and five frozen reviews.
.venv\Scripts\python.exe scripts/apply_verified_repairs.py
# Already applied locally. Reruns preserve source hashes/grants and preparation history.
.venv\Scripts\python.exe scripts/apply_verified_repairs.py --apply --activate
.venv\Scripts\python.exe scripts/audit_content_quality.py
.venv\Scripts\python.exe scripts/audit_educational_coverage.py
.venv\Scripts\python.exe scripts/evaluate_verified_quality.py --broad
```

Default repair mode is preview. Activation writes only approved existing private
resources through the normal pipeline. These commands do not acquire new
sources or authorize additional shared use.

Current private outputs:
`D:\AI\OSCAR\Knowledge\Catalog\reports\quality-review\2026-10-26\corrected`

Read `COMPLETION_REPORT.md`, `REPAIR_MANIFEST.json`,
`SOURCE_CLASSIFICATION_REVIEWS.json`, `REVIEW_COVERAGE.json`,
`VERIFIED_RETRIEVAL_RESULTS.json` and `REVIEWED_PASSAGE_POOL.json` there.
Older Gemini reports are explicitly superseded and retained for traceability.

Verification: 125 isolated tests passed, one optional local-model test skipped;
Ruff check/format and mypy passed. All 321 read-only retrieval requests across
107 questions and three modes returned current valid citations, with no fallback
or invalid citation. In the seven-question reviewed pool, top-five passage hits
were 4/7 keyword, 6/7 semantic and 6/7 hybrid. These are pooled regression scores,
not held-out library-wide accuracy. Normal OSCAR authentication, owner isolation,
all three local health endpoints and the live private summary notice passed.

Remaining source-quality limits include OCR symbols/tables, incomplete or
unverified editions, two preserved shared encoding defects and source-level
curriculum judgment. They must not be relabeled verified merely because the
screening software ran successfully. No original PDF is edited by this work.
