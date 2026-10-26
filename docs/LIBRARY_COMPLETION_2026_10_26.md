# Library completion continuation — 2026-10-26

This continues the approved private import on `main`. Original files, shared MBA
data, local Qwen pin and generation-provider configuration are preserved. Current
counts and completeness are derived from
`D:\AI\OSCAR\Knowledge\Catalog\ingestion-status.json`, not registration receipts.

## Final local outcome

All **672 original PDFs / 198,758 physical pages** now have verified coverage:
517 MBA PDFs reuse current approved shared text with every required supplement,
and the remaining original content has private indexed or reviewed non-text
outcomes. There are **1,040 searchable private references**, **24,542 active
document parts**, and **261,212 current local Qwen chunks/vector rows**; 18
additional references are explicitly reviewed non-text. No partial references or
unresolved pages remain. Reference counts include HTML sections, bounded
compilation windows and supplements; they are not distinct-book counts.

All **43/43 Social Systems** roadmap readings have indexed matches. The full
156,324-page compilation is covered by 159 disjoint ranges without gaps or
overlap. The final page audit passes 645 prepared PDF references / 187,098 pages;
the embedded-text audit passes 627 text references / 184,927 embedded pages.
All original bytes, sizes and modification times are unchanged. Preservation
checks found zero missing or changed baseline documents (1,384), chunks (36,790)
or vector rows (36,797, including seven historical rows).

In OSCAR, enable **Reference knowledge → All permitted references** to include
the new private MBA PDFs and supplements alongside the curated MBA corpus.
The MBA-only scope retains the approved shared collection. This completes the
audited local inventory, not every possible MBA source, edition, diagram label
or academic degree requirement.

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
of every map label. The final 12 exact-pixel review groups all have outcomes bound
to source checksum and physical page. Local OCR recovered text on 1,808 pages.
Graphic descriptions do not certify every label or formula.

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
The recorded ownership grant freezes the 599 MBA PDF resource IDs/checksums in
`private-use-approval.json` alongside the original Knowledge PDF grants. Repeated
registration rejects new files and changed bytes outside that recorded scope.

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
.venv\Scripts\python.exe scripts/complete_library.py --run --resource-kind reviewed

.venv\Scripts\python.exe scripts/audit_library_coverage.py --require-complete
.venv\Scripts\python.exe scripts/audit_prepared_books.py
.venv\Scripts\python.exe scripts/report_library.py `
  --baseline D:\AI\OSCAR\mba-corpus\2026-10-25\private-backups\pre-library-baseline.json
```

Registration requires hash-bound roadmap boundary review; it does not assert
successful indexing. `ingestion-status.json` reports active compilation coverage
and remaining pages. Operation receipts can contain historical failed attempts.
The `reviewed` batch selects approved, already active references with staged page
reviews. It uses a separate operation receipt, allowing completed ranges to be
updated while the main batch continues through different ranges.
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

Knowledge isolated suite: **108 passed, 1 skipped**; Ruff and mypy passed. Backend:
**440 unit tests**, typecheck/lint/build/format passed. Frontend: **34 tests**,
typecheck/lint/build passed. The earlier 173 E2E and 142 isolated backend
integration passes remain the baseline; they were not rerun for the notice text
change. Current ordinary authentication and owner-scoped collection readiness
passed. Five saved scripted configured-model cases passed: finance, management,
unanswerable abstention, opt-out and compilation physics. Saved citations reload,
idempotent replay and scope-change conflict passed. The original physics attempt
timed out under the old 2500 ms source budget and safely reported unavailable
sources; that failed request/message remains in history. Its separate stable
recovery request passed after the local source budget became 8000 ms. The
tracked default remains unchanged. The cited physics equation and direction of
acceleration were checked against original physical page 110908; attribution is
explicitly unverified for the mixed compilation.

The expanded-library six-question sample returned all 18 requests without
fallback: keyword gold-book hits **2/6**, semantic **5/6**, hybrid **4/6**.
Median latency was **0.453 / 1.044 / 1.527 seconds** respectively. Relevant
conditional-probability and writing alternatives were manually reviewed without
inflating strict gold-book scores. The 22 original MBA queries all retained
their baseline top document within the top six, with current approved citations
and no fallback; this is a scope/stability regression, not a new accuracy score.
The original strict MBA source-family benchmark remains **20/22**.

Exact search scores eligible IDs before fetching bounded text/metadata, uses a
transaction-local join plan restored before hydration, and deduplicates exact
text after access filtering. All original database rows/provenance remain.
Candidate pools are bounded at 300, so very large duplicate groups can still
limit diversity. No approximate vector index or new embedding model was added.

Final local evidence is under `D:\AI\OSCAR\Knowledge\Catalog\reports`:
`INGESTION_REPORT.md`, `RETRIEVAL_EVALUATION.md`, `SECURITY_REVIEW.md`,
`page-coverage-audit.json`, `extraction-audit.json`, `preservation-audit.json`,
`original-file-audit.json`, `retrieval-manual-review.json` and
`mba-retrieval-regression.json`. Private source text and chat receipts stay out
of Git. These checks establish local operation, not public production readiness.
