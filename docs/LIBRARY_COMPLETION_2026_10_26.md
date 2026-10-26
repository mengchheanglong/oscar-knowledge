# Library completion continuation — 2026-10-26

This continues the approved private import on `main`. Original files, shared MBA
data, local Qwen pin and generation-provider configuration are preserved. Current
counts and completeness are derived from
`D:\AI\OSCAR\Knowledge\Catalog\ingestion-status.json`, not registration receipts.

## Corrected source attribution

The initial 211-outline-node / 209-remaining-book estimate was unreliable. The
1.7 GiB source contains nested binders, repeated books and unrelated inserted
material. The initial Political Science range extended into unrelated books; it
was gated off and corrected to **physical PDF pages 10421–11059** (639 pages).
Psychology remains **35189–35971** (783 pages). The exact source checksum and
reviewed boundaries are in `compilation-reviewed-ranges.json`.

The replacement `compilation-coverage-plan.json` registers 157 disjoint physical
windows plus the two roadmap references over all 156,324 pages exactly once.
Windows are labeled **Mixed local compilation**, not verified OpenStax editions
or distinct books. Citation notices retain that uncertainty. Old saved replies
retain historical citations; future retrieval uses the corrected generation.

The seven original partial references now have explicit reviewed outcomes for
their flagged pages: decorative rules/logos, cover/header transcriptions and a
labeled visual map description. A visual description is not a full transcription
of every map label. Additional flagged pages are grouped by exact rendered pixels
for review; accepted outcomes are bound to source checksum and physical page.

## MBA original PDF coverage

Both roots contain **672 original PDF files, 198,758 physical pages**. The older
MBA root contains 599 of those PDFs. An exact original-to-prepared-text audit
links 517 PDFs to current approved shared documents. The completion plan adds
82 previously unlinked PDFs privately and 407 omitted/low-text pages through
332 bounded page supplements. Existing shared text, source notices, document
identities and quarantine decisions are retained. An earlier filename-based
83-file estimate was superseded by the checksum-based audit.

`audit_mba_pdf_coverage.py` verifies the original source SHA, download provenance,
prepared-file SHA and approved active document before comparing every original
embedded-text page. Graphic interpretation is a separate limitation. Reuse status
also requires the same document revision/embedding identity and active vectors.
Missing supplements, revoked approval and changed source evidence cannot count
as complete. Blank or explicitly reviewed decorative ranges have a
`REVIEWED_NON_TEXT` outcome; they produce no fabricated text, chunks or citations.

## Processing and preservation

- Preparation revisions retain old cache files and active generations. Physical
  eight-page buckets limit the effect of recovered blank/graphic pages.
- A finite pipeline overlaps bounded extraction with serialized local embedding.
  Whole-reference preparation retains one PDF handle across 50-page atomic
  checkpoints. The watchdog allows 120 seconds between progress updates, a finite
  bounded update count, and observed resident memory up to 2 GiB for verified
  large-source ranges (512 MiB for ordinary books). This is sampled monitoring,
  not a hard OS memory reservation.
- Source SHA verification is reused only in-process while file identity, size and
  nanosecond timestamps stay unchanged. Final audits rehash original files.
- Migration **0006** adds an `md5(text)` lookup index. Vectors are reused only for
  byte-identical text and the exact embedding identity, with actual text equality
  checked after lookup. MD5 is not an authorization or cryptographic trust check.
  Every target keeps independent provenance, grants, chunk IDs and vector rows.
- Thirty-eight legacy preparation identities were verified against source SHA,
  original embedded PDF text, active chunk signatures and owner scope before
  binding the additive metadata. Document/chunk/vector IDs, content and active
  generations were unchanged.
- Repeated registration preserves existing window identities, reviews, cache
  revisions and grants. Parent revocation also denies its derived ranges. Empty
  OCR output cannot discard an existing short embedded-text header.
- Reusing unchanged parts also requires unchanged extraction labels, formula
  review flags and source notices. Changed attribution never inherits a stale
  notice simply because the text matches.

## Manual operation

Run from the Knowledge repository's existing Windows `.venv`. The native worker
requires local Knowledge PostgreSQL on 43114 and local Ollama. No source PDF,
model weights or embedding array dump is written to Git or the catalog.

```powershell
.venv\Scripts\python.exe scripts/complete_library.py --register
.venv\Scripts\python.exe scripts/audit_mba_pdf_coverage.py
.venv\Scripts\python.exe scripts/register_mba_pdf_gaps.py --apply
# Optional finite extraction-only stage: no model requests or DB writes.
.venv\Scripts\python.exe scripts/complete_library.py --run --prepare-only --resource-kind mba
# Optional disjoint MBA indexing batch uses its own operation receipt.
.venv\Scripts\python.exe scripts/complete_library.py --run --resource-kind mba
.venv\Scripts\python.exe scripts/complete_library.py --run --workers 2
# Rerun to resume checkpoints or activate reviewed preparation revisions.

.venv\Scripts\knowledgectl.exe library prepare-book RESOURCE_UUID --whole-book
.venv\Scripts\python.exe scripts/library_visual_review.py
# Inspect images and explicitly classify groups in reports/visual-review.json.
.venv\Scripts\python.exe scripts/library_visual_review.py --apply

.venv\Scripts\python.exe scripts/audit_library_coverage.py --require-complete
.venv\Scripts\python.exe scripts/audit_prepared_books.py
.venv\Scripts\python.exe scripts/report_library.py `
  --baseline D:\AI\OSCAR\mba-corpus\2026-10-25\private-backups\pre-library-baseline.json
```

Registration requires hash-bound roadmap boundary review; it does not assert
successful indexing. `ingestion-status.json` reports active compilation coverage
and remaining pages. Operation receipts can contain historical failed attempts.
The additive legacy helper defaults to verification only; its explicit `--apply`
binds identity metadata only after all checks pass.

`page-coverage-audit.json` verifies an explicit outcome for every processed page
and an active chunk for every extracted text page. `extraction-audit.json`
separately compares embedded text with original PDFs. OCR, reviewed transcriptions
and visual descriptions are distinguished; mathematical layout, diagrams, small
map labels and publication/edition completeness still require source judgment.
Full processing does not certify every source claim or academic equivalence.
`--require-complete` fails if any original PDF still needs work or unresolved
pages remain. Final original-file audit covers both roots and checks bytes,
length and modification time. These checks do not modify the source PDFs.
Repeated original-text audits rehash sources and prepared files before reusing a
previous successful comparison. Hashes of previously verified page text can also
check unchanged embedded pages after a reviewed preparation revision; raw book
text or vectors are never exported for this computation cache. A source, part,
revision or grant mismatch cannot satisfy the final completeness gate.

## Validation

Knowledge isolated suite: **105 passed, 1 skipped**; Ruff and mypy passed. Backend:
**440 unit tests**, typecheck/lint/build/format passed. Frontend: **34 tests**,
typecheck/lint/build passed. The earlier 173 E2E and 142 isolated backend
integration passes remain the baseline; they were not rerun for the notice text
change. Current ordinary authentication and owner-scoped collection readiness
passed. Final live retrieval/coverage and preservation measurements belong in the
generated reports after the finite import and visual-review pass finish.
