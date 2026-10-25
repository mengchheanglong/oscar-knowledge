# Local Qwen operation on Windows

Ollama supplies embeddings only. OSCAR still generates answers with its existing
DeepSeek provider and credentials. Local Knowledge embeddings require no API key
and have no per-token API charge; they consume local electricity, RAM and GPU.
Provider selection never falls back to a paid embedding service.

## Installed machine

| Item | Location / value |
| --- | --- |
| Ollama 0.40.11 binaries | `D:\Apps\Ollama` |
| Model root | `D:\AI\Ollama\models` |
| Model manifest | `D:\AI\Ollama\models\manifests\registry.ollama.ai\library\qwen3-embedding\0.6b` |
| Weights | `D:\AI\Ollama\models\blobs\sha256-06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439` |
| Model | `qwen3-embedding:0.6b`, 1024 dimensions, Q8_0 |
| Listener | `127.0.0.1:11434` only |
| Logs / download / backup | `D:\AI\Ollama\logs`, `downloads`, `backups` |

The official tray app starts at user logon. An additional user Startup shortcut,
`OSCAR-Qwen-Warmup.lnk`, runs `D:\AI\Ollama\Warmup-Qwen.ps1` hidden. It waits for
Ollama and warms this model with constant nonsource text. It does not download
anything. Model weights persist across restarts; logon is required for this tray
deployment. Startup links were inspected, but Windows was not rebooted for testing.
Small Ollama logs/configuration, Windows shortcuts and existing `.ollama` identity
files remain on C:. Repositories and databases were not relocated.

## Reproduce installation

First inspect D: space, existing installation, models and environment. Preserve
existing models. Download the official installer from the
[Ollama releases](https://github.com/ollama/ollama/releases) and verify its
Authenticode signature and release checksum before running it. The installation
used the supported [/DIR option](https://github.com/ollama/ollama/blob/main/docs/windows.mdx):

```powershell
Get-PSDrive D
Get-Command ollama -ErrorAction SilentlyContinue
Get-AuthenticodeSignature D:\AI\Ollama\downloads\OllamaSetup-v0.40.11.exe
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'D:\AI\Ollama\models', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
$env:OLLAMA_MODELS = 'D:\AI\Ollama\models'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
& D:\AI\Ollama\downloads\OllamaSetup-v0.40.11.exe /DIR="D:\Apps\Ollama"
& D:\Apps\Ollama\ollama.exe pull qwen3-embedding:0.6b
& D:\Apps\Ollama\ollama.exe list
Get-ChildItem D:\AI\Ollama\models -Recurse -File
```

Restart an existing tray app after changing these variables. For a stopped
installation, launch `D:\Apps\Ollama\ollama app.exe` from the Start menu or with
`Start-Process -WindowStyle Hidden`. Do not run a second server on the same port.
Only the specified model is needed.

## Configure Knowledge

Set the following in this repository's ignored `.env`. Keep the existing internal
service token and database URL. These settings apply only to `oscar-knowledge`.

```dotenv
KNOWLEDGE_EMBEDDING_PROVIDER=ollama
KNOWLEDGE_EMBEDDING_MODEL=qwen3-embedding:0.6b
KNOWLEDGE_EMBEDDING_DIMENSIONS=1024
KNOWLEDGE_EMBEDDING_MODEL_REVISION=ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d
KNOWLEDGE_OLLAMA_BASE_URL=http://127.0.0.1:11434
KNOWLEDGE_EMBEDDING_BATCH_SIZE=16
KNOWLEDGE_EMBEDDING_TIMEOUT_SECONDS=15
KNOWLEDGE_EMBEDDING_QUERY_TIMEOUT_SECONDS=2
KNOWLEDGE_EMBEDDING_DOCUMENT_TIMEOUT_SECONDS=600
KNOWLEDGE_EMBEDDING_MAX_DOCUMENT_CHUNKS=256
KNOWLEDGE_OLLAMA_KEEP_ALIVE=-1m
KNOWLEDGE_OLLAMA_QUERY_INSTRUCTION=Given a question, retrieve relevant passages that answer the question
```

Pin the digest returned by `/api/tags` for a newly pulled release; a changed digest
is rejected until configuration is deliberately updated and sources re-embedded.
Leaving revision empty resolves it from the local runtime. Documents use raw text;
queries use `Instruct: <instruction>\nQuery:<question>`, following
[Qwen's task instruction guidance](https://github.com/QwenLM/Qwen3-Embedding).
An empty instruction uses the raw query and a separate identity. Inference uses
the [native embed endpoint](https://docs.ollama.com/api/embed), `truncate=false`
and a 4096-token context. Oversized inputs fail instead of silently truncating.

The machine uses `-1m` to keep the loaded model resident. The string `-1` is not a
valid Ollama duration. Keeping the model warm reserves roughly 1.2 GB of VRAM.
The portable default remains `10m`; a cold start may exceed the two-second query
budget and trigger keyword fallback. Warm it before accepting semantic queries:

```powershell
.\scripts\warmup-ollama.ps1
docker compose up -d --wait postgres
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\knowledgectl.exe reembed --collection mba-business
.\.venv\Scripts\knowledgectl.exe doctor
docker compose --profile app --profile worker build api worker
docker compose --profile app up -d --wait api
```

Alternatively run Uvicorn directly on Windows using the README command. Do not
bind both API processes to port 8010. Worker execution is one-shot:
`docker compose --profile worker run --rm worker` or Windows `knowledgectl worker`.
Use one ingestion worker at a time; the semaphore is process-local. Import and
parse in the same filesystem environment as the queued source paths. Re-embedding
uses stored text and works from either environment.

## Model migration and rollback

Back up the Knowledge database before schema changes. Migration 0002 adds a
model-specific table; it never alters the legacy 1536-vector column. Run only
`alembic upgrade head` on the Knowledge DB. It is separate from OSCAR's databases.

```powershell
.\.venv\Scripts\knowledgectl.exe reembed --collection mba-business --limit 100
.\.venv\Scripts\knowledgectl.exe reembed --collection mba-business --document-id <UUID>
.\.venv\Scripts\knowledgectl.exe reembed --collection mba-business --queue-only
.\.venv\Scripts\knowledgectl.exe worker --limit 20
.\.venv\Scripts\knowledgectl.exe worker --retry-failed --limit 20
.\.venv\Scripts\knowledgectl.exe jobs
```

Repeat with further source selections when a collection exceeds the source limit.
The command processes sources in stable ID order, so raising `--limit` or selecting
document IDs is needed to reach sources beyond the initial limit. Existing compatible
vectors skip inference. Failed jobs preserve the prior valid index. Re-embedding
adds all missing vectors for one source atomically; retries restart that source.
Limits remain 256 embedded chunks/source, max 32 inputs/request (default 16),
100,000 model-vector rows and the existing extraction/storage limits.

For immediate rollback, set `KNOWLEDGE_EMBEDDING_PROVIDER=disabled` and recreate
the API. Keyword retrieval continues; explicit semantic requests report 503.
Retain migration 0002 and all vector rows. Destructive Alembic downgrade is blocked.
Older application code can use its original table, though it may require the old
readiness migration check to be updated; prefer disabling in the current version.
Do not downgrade/stamp migration history or restore over a populated database.
The pre-change backup is `D:\AI\Ollama\backups\knowledge-before-qwen-0002.dump`.

To deliberately switch back to OpenAI, set provider `openai`, model
`text-embedding-3-small`, dimensions `1536`, revision empty (unless known), existing
OpenAI-compatible base URL and a separate embedding API key. Restart the API.
Exact matching legacy vectors are usable immediately; run `reembed` for missing
vectors only if external embedding calls are authorized. Qwen rows remain intact.
No OpenAI requests were used to verify this migration; OpenAI compatibility is
tested with mocked HTTP and real PostgreSQL vector queries.

## Diagnose and verify

```powershell
& D:\Apps\Ollama\ollama.exe ps
nvidia-smi
Get-NetTCPConnection -LocalPort 11434 -State Listen
Invoke-RestMethod http://127.0.0.1:11434/api/version
.\.venv\Scripts\knowledgectl.exe doctor
.\.venv\Scripts\knowledgectl.exe query 'subscription pricing' --mode semantic
.\.venv\Scripts\knowledgectl.exe query 'subscription pricing' --mode hybrid
.\.venv\Scripts\python.exe scripts/verify_ollama.py
$env:KNOWLEDGE_TEST_LOCAL_MODEL = '1'
.\scripts\test.ps1 -q
Remove-Item Env:KNOWLEDGE_TEST_LOCAL_MODEL
```

`verify_qwen_service.py --live` is an explicit live DB acceptance script: it imports
one original CC0 warehouse note, evaluates fixtures with two query instructions,
preserves both vector identities, and writes `QWEN_SERVICE_VERIFICATION.json`.
`smoke.py` remains an explicit keyword/auth/provenance check.

Compose maps the local provider URL to `http://host.docker.internal:11434` (override
with `KNOWLEDGE_DOCKER_OLLAMA_BASE_URL` if needed). Both version access and real
embedding inference were verified inside the actual worker container on this
Docker Desktop installation. This is platform-dependent: if unavailable, run the
API/worker on Windows and retain PostgreSQL in Docker. Never expose Ollama publicly
to fix container routing. The verified Windows listener remains loopback-only.

To free VRAM, run `ollama stop qwen3-embedding:0.6b` (the next semantic request may
reload it). To stop the runtime, choose **Quit Ollama** in its tray menu. Normal
OSCAR chat keeps its independent DeepSeek provider; hybrid Course Knowledge
degrades to keyword on embedding failure, with `fallback_reason` recorded in the
retrieval response. Restart the tray app and run the warmup script to resume.
Doctor readiness is database readiness plus a runtime/model check, not a benchmark.
