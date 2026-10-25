# Architecture and boundaries

An independent Python process and PostgreSQL database own curated reference
collections, document provenance, chunks and durable ingestion jobs. OSCAR retains
workspace files, existing ingestion/search, reviewed MAVIS memory, dialogue,
orchestration, generation and citation persistence. There is no direct database
connection from knowledge to OSCAR. No OSCAR database schema is modified.

The checked-out application uses NestJS 11/TypeORM, with retrieval located at
`src/modules/mavis/retrieval/retrieval.service.ts`. AssistantService retrieves
workspace chunks, ContextAssembler applies its 4,000-token approximate budget,
and DeepSeekLlmProvider maps `[Evidence #N]` to that same ordered evidence list.
AssistantService reconstructs citations using included chunk IDs. PostMessageDto
and the environment Zod schema validate requests/configuration. The request
fingerprint is generated before saved-turn reuse inside `postMessage`. Citation
JSON already supports additive metadata, so no schema migration is needed there.
The current Compose project is `oscar`, using local ports 43100–43106, not the
older `continuum-backend` identity in the prompt. Both existing branches were
`develop`; pre-existing AGENTS.md edits were preserved. No local MBA collector was
found in the available workspace (dependency/runtime directories excluded).

## Data flow

1. Curator explicitly approves a local file or reviewed manifest entry.
2. CLI creates a durable job; CLI/worker processes bounded batches, outside HTTP.
3. A spawned parser process emits segments with pages/headings/times/row IDs.
4. Deterministic bounded chunks preserve segment provenance. Nearby text in one
   section is combined; PDF page boundaries and catalog rows remain separate.
5. Explicit disabled/OpenAI/Ollama selection; batches validate model, order, count,
   finite nonzero vectors and provider dimensions (1536 OpenAI, 1024 local Qwen).
6. A transaction inserts a complete revision and activates it atomically.
7. Authenticated retrieval scopes collection + approval + active revision before
   FTS or vector ranking, then optionally combines candidate lists with RRF.
8. OSCAR opt-in HTTP client validates a bounded response and maps external evidence
   to a separate assistant evidence type. Legacy workspace retrieval is unchanged.

## Failure and concurrency

Parser timeouts terminate the child process. Jobs record attempts, safe errors,
lease start, checkpoints and completion. Recovery reprocesses the source from its
beginning rather than claiming partial embedding resumption. Pending jobs dedupe
per document under a collection lock. Job claim uses row locks; document locks
serialize revision activation. A global advisory lock serializes storage quota
accounting. Never activate partial chunks; old revision remains queryable after
parser/provider/storage failure. Explicit deletes and withdrawn approval always
override revision availability. Old revisions count against storage quota.

Embeddings are limited to 256 chunks/document, 16 inputs/batch by default (max 32),
three attempts, 15-second request timeouts and a 600-second document budget.
Local queries have a two-second embedding budget, including lock contention and
retries. One process-local semaphore serializes local inference; run one ingestion
worker process to bound GPU pressure. This is not a cross-process scheduler.
Job leases default to 900 seconds. HTTP transport timeouts bound individual I/O;
the operation deadline is checked between requests/retries. Native Ollama can
continue already submitted work after a client timeout. No infinite retry loop.

Migration 0002 adds `chunk_embeddings`, keyed by chunk ID and model identity,
with separate typed 1024/1536 columns and a dimension/column check. The legacy
`chunks.embedding vector(1536)` and its identity remain untouched. Exact cosine
queries select only the matching identity, dimension and typed column. Original
OpenAI identities remain queryable for their exact endpoint/model configuration.
Identity includes provider, model, digest/revision, dimensions, raw preprocessing,
query instruction hash and endpoint identity (local aliases share one identity).

`reembed` reads active stored text, adds missing model vectors atomically, and
preserves chunk IDs, revisions, locators and source hashes without downloading.
Changing models during ordinary source import can create a new revision; use
`reembed` for a source-preserving model migration. Failed re-embedding keeps the
old vectors and active revision. Final activation rechecks approval and job lease.

## Deployment and security

Compose `oscar-knowledge` owns its own persistent volume, ports 43114 (DB),
43115 (disposable test DB), and 8010 (HTTP). All published bindings use loopback.
API starts without creating tables and reports unready before migrations/token.
Container runs as UID 10001 with a read-only root for the API and a temporary
directory. Uvicorn handles graceful shutdown. Worker is separately invoked, not
part of request handling. No public unauthenticated retrieval endpoint exists.
Transport across hosts requires TLS and network restrictions. No private corpus
or per-user ACL support is claimed. See SECURITY.md for operational limits.

FTS has a GIN index and metadata/version lookups have btree indexes. Semantic
search deliberately uses exact pgvector cosine ranking as the small-corpus
baseline. An HNSW index can be enabled after measurement using an explicit reviewed
DDL operation on this database (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`).
ANN filtered recall and query plans require corpus-specific evaluation before
larger deployment. Millions of chunks is a future target, not a benchmark result.
