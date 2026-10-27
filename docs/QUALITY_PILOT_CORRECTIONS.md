# Content-quality inspection corrections

Search and full-passage inspection now share `current_source_conditions` in
`app/library/eligibility.py`. A current actor's private-reader grants, enabled
collections, matching chunk/document/book collection, matching visibility,
approval, active generation/revision and exact chunk exclusions apply to both.
The service token alone does not authorize private book text. The backend signs
the actor and complete request body; preserve that boundary.

The 2026-10-27 corrective checks passed 148 tests, with one skipped, plus Ruff
and mypy. Adversarial inspection tests exercise inconsistent collections/book
visibility, a disabled private collection, private books linked to shared
documents, revoked readers and deleted/unapproved documents.

`KNOWLEDGE_QUALITY_EXCLUDED_CHUNK_IDS` can quarantine exact unsafe chunks while
preserving the source, vectors, revisions, ownership and provenance. A review
badge alone is not a quarantine. Keep source-bound exclusions and rollback lists
in private installation records. Recreate the API after configuration changes.
Whole-chunk exclusion also omits useful prose and does not repair formulas.

The private corrective pilot resides in
`D:\AI\OSCAR\Knowledge\Catalog\reports\quality-pilot\codex-remediation-2026-10-27-183500`.
Original Gemini reports remain separate. Source-hash checks, fresh page renders,
page judgments and actual-app evidence must be distinguished. Unreviewed pages
remain unverified; page roles in a report are not automatically enforced ranking
metadata. Do not describe a short slide as a full explanatory lesson or claim
that all pages are clean because ingestion succeeded.
