# Permissioned original passage windows — Phase 3

Implemented 2026-10-30. `POST /internal/v1/passage/window` extends authenticated
passage inspection with bounded neighbors within the same prepared document and
revision. OSCAR exposes an authenticated API equivalent and read-only
`get_knowledge_window` MCP tool.

Request existing chunk/document/revision identifiers and signed private-reader
identity, radius 0–2 (default 1), `max_chars` 1–16,000 (default 12,000) and
`max_bytes` 1–64,000 (default 48,000). The signature covers the original raw body.
The public backend rejects owner overrides.

Return one to five whole original chunks sorted by relative ordinal, each with
its own metadata, locator, character count, UTF-8 byte count and SHA-256.
Totals and `context_limited` report budget omissions. Whole neighbors can be
omitted for text/serialized limits; originals are never joined, summarized or
clipped. Serialized JSON is bounded to 96,000 bytes. An oversized anchor is 413.

The candidate query and each individual inspection enforce current eligibility.
Private ownership/exact-book grants, current generation, revision, approval,
exclusion and deletion apply independently to each neighbor. Recheck the anchor
before return; do not leak inaccessible neighbor metadata. The four-second outer
deadline returns generic 503. Running read-only DB threads are not forcibly
cancelled and retain the existing SQL statement timeout.

This cannot cross prepared-document boundaries or reconstruct complete chapters.
`context_limited=false` does not certify source completeness. It does not repair
PDFs, diagrams, equations, OCR or reading order, or change ingestion/embeddings.

Verification: 185 tests passed, one skipped; Ruff checks/format and mypy passed.
Tests cover private grants/revocation, signed-body tampering, stale states,
excluded neighbors, Unicode/hash/byte limits, serialized limits and deadlines.
Fresh live MCP inspection matched three spans to individual source reads;
backend development evaluation matched 112 evidence occurrences to originals.
These verify provenance mechanics, not independently measured answer accuracy.
Source counts, sampled PDF hashes, catalog/grants and configuration hashes were
unchanged; no migrations or reembedding ran. Private receipts are under
`D:/AI/OSCAR/Knowledge/Catalog/reports/knowledge-intelligence-phase3/2026-10-30`.
