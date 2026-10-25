# Qwen implementation and verification — 2026-10-25

Local Qwen embeddings are installed, enabled and usable by OSCAR Knowledge.
Real document/query vectors reach pgvector, semantic/hybrid retrieval and an
OSCAR conversation with persisted, validated citations. The configured embedding
API key is empty. OSCAR still generates answers with `deepseek-flash`; its
generation key, workspace/history embedding configuration and MAVIS are unchanged.
No repository or database was moved. The changes belong to the independent
`oscar-knowledge` repository.

## Installation and environment

Before installation, D: was writable with approximately 262 GiB free. No Ollama
binary, running process, port listener or installed-application entry was found.
The previous user variable `OLLAMA_MODELS=D:\OllamaModels` pointed to an absent
directory. Existing small `.ollama` identity files on C: were preserved untouched.
No pre-existing models were removed or duplicated.

| Item | Verified value |
| --- | --- |
| Application | `D:\Apps\Ollama\ollama.exe`, version 0.40.11 |
| Official installer | `D:\AI\Ollama\downloads\OllamaSetup-v0.40.11.exe` |
| Installer verification | Release SHA256 `87309d23b423abeae1d8df2f98df95f94bf35659debfdf3761d65b7b62a75508`; valid Authenticode, Ollama Inc. |
| Model | `qwen3-embedding:0.6b`, 595.78M parameters, Q8_0, 1024 dimensions |
| Digest | `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d` |
| Model root | `D:\AI\Ollama\models` |
| Actual weights | `D:\AI\Ollama\models\blobs\sha256-06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439` |
| Manifest | `D:\AI\Ollama\models\manifests\registry.ollama.ai\library\qwen3-embedding\0.6b` |
| GPU | NVIDIA GeForce RTX 3050 6GB Laptop GPU, driver 596.49; Ollama reports 100% GPU |
| Network | Windows listener `127.0.0.1:11434`; actual Docker worker inference via `host.docker.internal:11434` |

Persistent user variables changed: `OLLAMA_MODELS=D:\AI\Ollama\models`,
`OLLAMA_HOST=127.0.0.1:11434`, `OLLAMA_NO_CLOUD=1`. Prior values are saved in
`D:\AI\Ollama\logs\prior-environment.json`. The official installer added
`D:\Apps\Ollama` to user PATH; the pre-existing `D:\Ollama` entry remains.
Private Knowledge `.env` now selects Ollama, exact model/digest, 1024 dimensions,
batch 16, local URL and `keep_alive=-1m`. Service credentials were retained and
not printed. Backend/frontend environment files were not changed by this task.

The official user Startup shortcut targets the D: tray binary. A second hidden
Startup shortcut runs `D:\AI\Ollama\Warmup-Qwen.ps1`; it was executed successfully.
Weights persist across restarts; user logon starts the app. Windows itself was
not rebooted. Small runtime logs/configuration and Windows management files remain
on C:, so total C: isolation is not claimed.

## Schema and source preservation

Before migration, the live Knowledge DB contained six approved original synthetic
documents, six active chunks and zero populated legacy embedding vectors. No
university corpus or private user documents were present in this database.
The custom-format pre-change dump is
`D:\AI\Ollama\backups\knowledge-before-qwen-0002.dump` (18,356 bytes).

Migration **0002**, following the unchanged 0001, adds `chunk_embeddings` with
primary key `(chunk_id, identity)`, separate `vector(1024)`/`vector(1536)` columns,
a matching-dimension constraint and an identity/chunk lookup index. It leaves
`chunks.embedding vector(1536)` and every original row intact. Semantic queries
select a compatible typed column and exact model identity. No HNSW was introduced.
Exact matching original OpenAI vectors remain supported.

After migration, all six original sources were re-embedded from stored chunks.
A comparison against rows extracted from the actual pre-change dump confirmed
unchanged document IDs, revisions, hashes, titles, URLs, course/license metadata,
chunk IDs/revisions and legacy vector columns. See
[migration evidence](QWEN_MIGRATION_VERIFICATION.json). A separate integration
test populated a real 1536-vector before upgrading 0001→0002 and verified its
values and identity survived. This distinguishes tested preservation from the
live DB's initially empty legacy vector column.

One additional original CC0 warehouse note was imported through the real parser,
chunker, Qwen provider and atomic activation pipeline. It contains no university
material. The live DB now has seven documents, seven chunks and fourteen 1024
model-vector rows: seven for each of the two tested query-instruction identities.
Both identities are intentionally retained; only the selected identity is queried.
Original revisions remain 1. No existing OSCAR tables or Docker volumes changed.

For reindexing, configure the desired provider and run
`knowledgectl reembed --collection mba-business`; use document IDs/limits/queue
options for controlled batches. It uses stored text and skips compatible rows.
Rollback means disable embeddings or explicitly reselect OpenAI while retaining
0002 and all model rows. Destructive downgrade is blocked. Full commands and
recovery notes are in [LOCAL_QWEN.md](LOCAL_QWEN.md).

## Executed verification

| Check | Actual result |
| --- | --- |
| Knowledge tests, real PostgreSQL + local model opt-in | **67 passed**, 6 dependency deprecation warnings, 27.66 seconds |
| Provider tests | Serialization, query/document formatting, batching/order, no paid fallback, empty key, model/revision validation, wrong dimensions/count, zero/nonfinite vectors, connection/timeout/retry failures, bounded configuration |
| Database tests | Additive legacy-vector migration, 1024 storage/cosine retrieval, identity separation, active revisions, approval/collection filters, failed re-embedding preservation, unchanged import concurrency/deletion |
| Real native Ollama | Single, batch 2, batch 16: finite nonzero 1024-vectors; batch/single cosine ~1 for each corresponding input; repeated calls did not change/download model files |
| Real ingestion + retrieval | New authorized original warehouse note indexed; semantic and hybrid rank its correct passage first with its actual document/chunk IDs and heading locator |
| Live source preservation | Pre-change dump compared against six original documents/chunks; fields unchanged |
| Docker | API and worker images built; API healthy; actual worker container generated a real 1024-vector through the host route |
| Offline behavior | Automated provider outage tests plus real refused local connection: hybrid records keyword fallback; semantic-only reports unavailable; keyword works without runtime |
| HTTP smoke | Readiness, missing-token 401, authenticated keyword result, provenance and natural-language fixture query passed |
| CLI doctor | Migration 0002 ready, provider Ollama, runtime reachable, 1024 dimensions, seven compatible active vectors |
| Ruff / format / mypy | Passed; mypy checks 25 application files |
| OSCAR live acceptance | Real configured DeepSeek generation, persisted external citation, saved answer replay and normal chat opt-out passed |

Executed commands included `KNOWLEDGE_TEST_LOCAL_MODEL=1` with
`scripts/test.ps1 -q`, `ruff check`, `ruff format --check`, `mypy app`, explicit
Alembic upgrades, `knowledgectl reembed/doctor`, `scripts/smoke.py`,
`scripts/verify_ollama.py`, `scripts/verify_qwen_service.py --live`, Docker API/worker
build/start/inference, and backend `node scripts/verify-knowledge-local.cjs --live`.
Tests isolate embedding configuration and block remote HTTP; only explicit local
model opt-in permits loopback Ollama. No paid embedding endpoint was contacted.
No new backend/frontend source changes required their full test suites to rerun.

Runtime artifacts:
[native benchmark](QWEN_RUNTIME_VERIFICATION.json),
[live service/evaluation](QWEN_SERVICE_VERIFICATION.json),
[live OSCAR answer/citation](QWEN_OSCAR_VERIFICATION.json).

## Retrieval and OSCAR demonstration

Question: “When should we replenish cartons if supplier lead time is five days?”
Both semantic and hybrid modes returned **Local Qwen warehouse verification**,
course `LOCAL-QWEN-TEST`, locator **Warehouse replenishment**, revision 1, rank 1.
The passage states 12 cartons/day × 5 days + 15 safety stock = **75 cartons**.
Semantic cosine was approximately 0.6644; hybrid RRF score approximately 0.03279.
Neither request degraded to keyword. This is original verification material.

The [live OSCAR conversation](http://127.0.0.1:43100/assistant?conversation=bb176456-7d8b-4eba-b891-549baca5b6a5)
used Course Knowledge and the existing `deepseek-flash` provider. It advised a
controlled basic/premium subscription test measuring conversion, retention and
support costs, citing **Pricing experiments**, `DEMO-PRICING`, revision 1,
chunk `e669b4eb-dbb4-5bac-9521-3943916428e0`, as **Evidence #5**. OSCAR persisted
that citation against the actual included evidence and reused the saved answer
for an identical retry. A subsequent ordinary opted-out chat completed with no
external citation. This was live generation, not mocked output. The synthetic
example.org URL is provenance metadata, not a hosted course resource.

## Measurements and limits

| Measurement | Observed value |
| --- | --- |
| Model download size | 639,150,858 bytes reported by Ollama (~610 MiB); weights blob 639,150,592 bytes |
| Warm native single embedding | ~25 ms (first measured request ~143 ms, already warm) |
| Native batch 2 / batch 16 | ~171 ms / 377 ms |
| Batch 16 throughput | ~42.4 short embeddings/second |
| New note ingestion | ~2.27 seconds including bounded Windows parser startup |
| Seven-source alternate-identity re-embedding | ~2.65 seconds |
| Semantic / hybrid mean latency, 20 fixture questions | ~339 ms / 353 ms using Python provider + DB |
| Docker HTTP semantic / hybrid sample | ~229 ms / 226 ms |
| VRAM | Ollama reports 1,228,857,671 bytes allocated; GPU total usage ~1267 MiB of 6144 MiB |
| Process RAM snapshot | llama-server ~645 MiB; two Ollama processes ~92 MiB combined; tray ~125 MiB (working sets, not total system memory) |

The initial cold request timed out after 60 seconds while the server logged a
52.86-second model load. Warm benchmark figures are not cold-start figures. The
logon warmup uses a 180-second timeout and keeps the model resident. Restarting or
unloading it can still cause semantic timeout until warmed; hybrid then records
keyword fallback. API readiness intentionally does not depend on Ollama availability.

On twenty easy synthetic gold questions, Hit@6 and Recall@6 were 1.0 for keyword,
semantic and hybrid. MRR@6 was keyword 1.0, hybrid 1.0, semantic with the query
instruction 0.9667, and semantic without it 0.8875. No fallbacks occurred during
these evaluations. This supports the configured instruction on this fixture only;
it does not establish general improvement or real university-corpus accuracy.

Remaining limits: no real approved university corpus/evaluation; exact cosine
search only; bounded 256 embedded chunks/document and 100,000 model-vector rows;
one ingestion worker process recommended; source-level retries, no batch resume;
startup registration verified without reboot; OpenAI live inference not exercised;
runtime-offline acceptance used a real refused local URL rather than stopping the
tray app during the live chat. CPU fallback was not needed or benchmarked. Bulk
MBA imports require approved material and a passage-level evaluation before scale
claims. These are operational limits, not incomplete P0 installation work.

## Files changed

Application: `app/config.py`, `app/api/schemas.py`, `app/db/models.py`,
`app/embeddings/{provider,base,factory,openai_provider,ollama_provider,storage}.py`,
`app/ingestion/{pipeline,reembedding}.py`, `app/retrieval/hybrid.py`, `app/cli.py`,
`app/main.py`, `migrations/versions/0002_model_embeddings.py`.

Operations: `.env.example`, `compose.yaml`, `scripts/smoke.py`,
`scripts/verify_ollama.py`, `scripts/verify_qwen_service.py`,
`scripts/warmup-ollama.ps1`. Private `.env`, generated note under ignored `data/`,
installed D: binaries/weights/logs/backups and user Startup configuration are local
operational changes and contain no committed credentials.

Tests: `tests/conftest.py`, `tests/unit/test_ollama.py`,
`tests/integration/test_pipeline.py`, `test_model_embeddings.py`,
`test_additive_migration.py`.

Documentation: `README.md`, `docs/{architecture,INGESTION,OSCAR_INTEGRATION,EVALUATION,
IMPLEMENTATION_REPORT}.md`, this report, `LOCAL_QWEN.md`,
`QWEN_{RUNTIME,SERVICE,MIGRATION,OSCAR}_VERIFICATION.json`, and the additive
`fallback_reason` field in `docs/verified-evidence.json`. No dependency was added.
