# Bounded search and independent retrieval channels

Long questions previously fell back to an OR of up to 32 terms, including
answer-format instructions. Ranking that union across the reference corpus
could hit the SQL timeout before semantic retrieval ran.

Keyword retrieval now tries the original query, adjacent pairs of up to sixteen
unique content terms, then a bounded single-term union if needed. Common search
instructions are omitted from the alternatives. These are AND pairs, not exact
phrase-distance searches. Original filters, collection permissions, approvals,
quality exclusions, generations and revisions apply to every query/hydration.
The original request remains semantic input in this service; the main app may
provide a shorter search representation separately from the full model question.

Each ranking statement runs inside a savepoint, using at most the existing
configured statement budget and a four-second keyword/eight-second vector cap.
Success restores the caller's timeout; failure rolls back its SQL state. This is
a per-statement bound, not a guarantee about whole-request latency or pool waits.
The other retrieval channel can continue after failure. Responses identify
keyword-only or semantic-only fallback with a machine-readable reason. If both
channels fail without a successful keyword search, the request fails unavailable.
Legacy embedding identity checks and private local-embedding restrictions remain.
Neither vector contents nor database schema changes are required.

Exact vector ranking still scans eligible embeddings; no approximate vector index
is introduced. Large libraries and concurrent requests can still be expensive.
Content pairs and term limits can miss unusual formulations; semantic retrieval
and the existing bounded topic graph provide additional discovery paths. This
release does not establish exhaustive recall or correct every source extraction.

Verification on 2026-10-29: full suite 171 passed, 1 skipped; lint and mypy passed.
New integration cases exercise actual timeout rollback, both one-channel failure
directions, total failure, named-source fallback, long questions and private-source
isolation. Live evaluation and sampled preservation receipts are outside Git at
`D:\AI\OSCAR\Knowledge\Catalog\reports\rag-improvement\2026-10-29`.
