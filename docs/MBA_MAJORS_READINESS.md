# Approved MBA-major library: local readiness

2026-10-26 PDF continuation: all 599 original MBA PDFs now have verified text
coverage through 517 existing shared-source links, 82 private full-PDF imports
and 407 page supplements. The existing shared import and its held-out subset are
unchanged. In Assistant, enable **Reference knowledge → All permitted references**
to include owned private MBA additions alongside the approved shared collection.
The **MBA** scope continues to select the curated shared subset. Whole-library
compilation progress and source-quality limits are documented in
[the continuation guide](LIBRARY_COMPLETION_2026_10_26.md) and local generated
reports. The measurements below retain their original 2026-10-25 scope/date.

Verified 2026-10-25. The user approved importing the reviewed subset for a
noncommercial local demonstration, retaining source notices and excluding
quarantined or unresolved third-party content.

## Available now

The shared `mba-majors` collection contains **1,374 approved documents**,
**36,722 active chunks**, and **36,722 compatible 1024-dimensional local Qwen
vectors**. All prepared checksums match. There are no failed or unfinished import
jobs. The original 10 documents and 68 chunks retain their IDs, revisions and
content hashes. A pre-import PostgreSQL dump is retained privately on D:.

The separate study library organizes **22 major pathways, 176 units, 176 unit
activities and 22 capstones**. It includes 24 web textbooks, 599 distinct PDFs
(14,932 extracted pages), 337 timestamped lectures, and 3,501 figure assets.
Its SQLite index contains 16,605 documents/pages and 26,475 passages. These local
index counts differ from the shared service's document/chunk boundaries.

Corpus, original source spreadsheets, licenses, guides, search tools and receipts:
`D:\AI\OSCAR\mba-corpus\2026-10-25`. Start with `MBA_ALL_MAJORS_REPORT.md`,
`MBA_MAJORS_SUMMARY.csv` and `MBA_MAJORS_COVERAGE.csv`. Downloaded content,
private receipts and backups stay outside Git.

## Use through OSCAR

The private backend configuration currently selects `mba-majors`; Knowledge is
available on port 8010. Open <http://127.0.0.1:43100/assistant>, use an ordinary
Assistant chat, and enable **Course knowledge** for the turn. Ask a focused
question, then open its numbered citation to inspect the source and locator.
The checkbox starts off. The existing configured generation model is preserved;
Knowledge supplies evidence and uses local embeddings, not answer generation.

From the sibling backend repository:

```powershell
node scripts/connect-knowledge-local.cjs --collection mba-majors --check
node scripts/verify-mba-majors.cjs
# Three bounded real-model requests; creates an acceptance chat in existing AIW.
node scripts/verify-mba-majors.cjs --live
```

To reconnect after a configuration change, omit `--check`, then restart the
backend using its normal local launcher. See the backend's
`docs/operations/KNOWLEDGE_LOCAL.md`. Knowledge startup remains documented in
this repository's README and `scripts/hackathon.ps1 -Start -Collection mba-majors`;
no database reset or reimport is required. For a read-only whole-stack check, run
`scripts/hackathon.ps1 -Collection mba-majors`.

## Measured checks

- Import integrity: all approved documents, active vectors and checksums match;
  83 held-out items are absent; the existing corpus digest is unchanged.
- Retrieval: one hybrid query per major, 22/22 scoped to `mba-majors` with no
  fallback. **20/22** hit the predefined expected source families. Manual review
  found relevant alternatives for the other two: MIT product-capacity linear
  programming solutions, and management chapters on informal networks,
  organization structure and culture. The strict baseline remains 20/22.
- Live OSCAR: finance and healthcare questions completed using the pre-existing
  `deepseek-flash` setting and returned persisted citations from this collection.
  Each cited chunk was checked against an approved, active database revision.
  Request replay returned the same saved message. An ordinary opt-out answer
  completed without external citations. Exactly three new generation requests
  were made by this verifier; replays used their existing idempotency keys.
- Study navigation: 176/176 unit files and source links exist, 528/528 lexical
  concept-location checks found passages, ten niche local-search queries passed,
  and SQLite integrity is valid. The capstone calculator passed 37 named numerical
  checks. Essays and recommendations have not been independently graded.

Private evidence: `shared-import/verified-import.json`,
`retrieval-evaluation.json`, `retrieval-manual-review.json`,
`live-integration.json`; backend `var/mba-majors/latest.json`.

## Scope

These are original study pathways using the referenced Wharton majors as a domain
checklist, not official syllabi, academic credit, or proof of MBA equivalence.
Coverage and sample retrieval do not establish universal answer accuracy. The
shared import includes the reviewed subset; the wider local review library also
retains held-out material. Proprietary simulations are replaced by an original
decision laboratory. Mathematical layout, captions and OCR have limitations;
consult original pages and figures. Historical and jurisdiction-specific sources
do not establish current professional rules. Original licenses, attribution and
third-party exceptions continue to apply. Public deployment and commercial reuse
were not approved by this local-demo import.
