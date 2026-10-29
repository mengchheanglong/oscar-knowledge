# Topic graph and retrieval expansion

This derived discovery index connects independent reference passages to 32
versioned English starter topics using exact lexical mentions. Curated topic
pairs permit one additional hop. Links do not assert support, contradiction,
agreement, credibility, or exhaustive conceptual coverage. Project documents
continue the main app's normal retrieval pipeline; they are not graph nodes.

## Operation

Apply additive migration `0007` through the explicit Alembic workflow, then run
`knowledgectl graph-build` with the intended local database configuration. The
build atomically commits graph metadata, reading approved active revisions and
book generations. It never changes source text, IDs, vectors, or original files.
A failed transaction can be retried. No graph build calls an LLM.

`KNOWLEDGE_GRAPH_ENABLED=true` enables browsing and expansion after a successful
build. Set it to `false` and restart the API to disable both without dropping
tables. Retrieval's `graph_expand:false` supports ablation comparisons.

Successful ingestion adds links for new chunks in a savepoint once the graph
is ready. If that update fails, ingestion stays successful with checkpoint
`graph_update=pending_rebuild`; rerun `graph-build`. Build statistics describe
the last full build, not a continuous ingestion dashboard. Current eligibility
is checked at query time; obsolete links cannot authorize obsolete passages.

## Browse and retrieval

`POST /internal/v1/graph` requires service authentication and signed reader scope
for private collections. Parameters: `collection_ids`, `query`, `topic_id`,
`source_id`, `limit` (1–40), `offset` (0–100000). Grants, approval, quality
exclusions, revisions, and active generations apply to counts, nodes and edges.

Responses include scoped counts, paginated sources, exact mention anchors,
SHA256, chunk/document IDs, revision and physical page/locator. Unmapped sources
remain visible with a sample passage. Each source/topic pair displays one
representative mention. Related-topic edges are `related_topic_hint`.

Broad retrieval requests expand after ordinary keyword/vector ranking from up
to three seed passages, four seed topics and eight topic candidates. Expansion
preserves leading normal results and adds at most two passages (one for smaller
result sets), one per additional source. Explicit multi-topic requests favor
those topics. Index-like pages and repeated normalized text are rejected during
expansion. This heuristic may reject useful table-like material; normal retrieval
remains available. Named-source and focused requests do not expand.

Candidates inherit existing collection/metadata filters; anchors and full hashes
are revalidated. `discovery_path` identifies the seed/topic hop, never entailment.
Main OSCAR caps graph-derived selections at two and retains existing bounded
context, citations and answer-support review.

Graph SQL runs in a savepoint: failures return ordinary retrieval with
`GRAPH_EXPANSION_UNAVAILABLE`. Retrieval and graph browsing disable per-query
parallel workers to avoid exhausting Docker's small shared-memory allocation
under concurrent library requests. This does not increase the SQL time budget.

## Initial local evaluation — 2026-10-29

The build scanned 297,993 active passages, mapped 66,845, and created 81,143
passage/topic links. For the configured reader across the three collections,
1,776 of 2,416 accessible reference records have starter links; 640 have none.
References include course chapters and compilation volumes, so these are not
distinct-book counts. Unmapped references still participate in regular retrieval.

Four live ablations found additional passages in three cases. Inspection exposed
an index and duplicate compilation text; rejection and deduplication were added
and comparisons repeated. This demonstrates discovery, not a measured gain in
recall or answer accuracy. Broader human relevance judgments remain necessary.

Source/embedding row counts stayed unchanged; 200 sampled passage hashes matched
before/after. This is sampled preservation verification, not a full cleaning or
faithfulness audit. Private reports remain outside Git at
`D:\AI\OSCAR\Knowledge\Catalog\reports\knowledge-graph\2026-10-29`.

Next improvements: reviewed topic aliases, disambiguation of words such as
"retention", better mixed-compilation attribution, and labeled cross-source
questions. Never infer author agreement or verified business outcomes from
topic co-occurrence.

The live assistant check included and cited one graph-discovered pricing
passage, with matching persisted evidence hashes and exact quote anchors. Its
support review filtered the draft and the resulting synthesis remained limited.
A longer instruction-heavy question hit the existing 10-second SQL timeout
before returning library evidence; a shorter question succeeded. Long-query
planning/performance and answer synthesis remain open issues. Do not describe
this release as complete semantic understanding of the library.
