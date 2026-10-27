# OSCAR Knowledge

Development uses `main` directly, consistently with OSCAR backend and frontend.

The local main app now searches all permitted library sources together with
project context through one enabled **Knowledge** toggle. Collection boundaries
still enforce access and preserve citations. Large local installations can set
`KNOWLEDGE_DATABASE_STATEMENT_TIMEOUT_MS=10000` (validated maximum 30000) and an
app request budget of 25000 ms; the tracked SQL default remains 5000 ms.

Full page-content cleaning is deferred for later work; see the
[saved handoff and next batch](docs/NEXT_PDF_CLEANING_PASS.md).

The [completed source review](docs/SOURCE_REVIEW_COMPLETION_2026_10_26.md)
records the 68 page repairs, two encoding corrections, and bounded reviews of
176 MBA units and 43 Social Systems readings. The
[content-quality remediation](docs/CONTENT_QUALITY_REMEDIATION.md) corrects
the later automated audit's metadata labels, citation checks and benchmark
claims. Processing completeness and independent semantic/visual review remain
separate statuses; current private quality reports use the `corrected` directory.

The private Windows library is connected to OSCAR. See the
[local library integration guide](docs/LOCAL_KNOWLEDGE_LIBRARY_INTEGRATION.md)
and [completion continuation](docs/LIBRARY_COMPLETION_2026_10_26.md)
for verified coverage of all 672 original PDFs, manual incremental commands,
private scope and OCR/graphic limits. All compilation ranges are processed;
source PDFs and private reports stay outside Git. In OSCAR, enable **Reference
knowledge → All permitted references** to include private MBA additions.

Independent, evidence-only retrieval service. Python 3.12+ (verified locally on
3.13), FastAPI, SQLAlchemy/Alembic, PostgreSQL 17 and pgvector. No answer generation,
memory writes, project tables, or background agent framework. Embeddings are
optional and separately configured. Synthetic fixtures need no provider credentials.

Local Qwen embeddings are installed and verified on this Windows machine. See
[Local Qwen operation](docs/LOCAL_QWEN.md) and the
[implementation and verification report](docs/QWEN_IMPLEMENTATION_REPORT.md).
The checked-in default remains `disabled`; provider selection is explicit.

The approved 22-major study library is now available in shared `mba-majors`:
1,374 documents and 36,722 locally embedded passages. See
[MBA major library readiness](docs/MBA_MAJORS_READINESS.md) for usage, import
integrity, live chat checks and scope. Enable **Course knowledge** in OSCAR chat.

The earlier local MIT demo, measured real-source retrieval results, startup and
remaining grounding limits are documented in
[KNOWLEDGE_HACKATHON_READINESS.md](docs/KNOWLEDGE_HACKATHON_READINESS.md).
Health check: `scripts/hackathon.ps1`; existing-machine startup: add `-Start`.

## Windows PowerShell

Run from this directory. Docker Desktop must be running; Python 3.13 and pnpm/Node
are needed for the respective repositories. The setup script creates a random
internal token in ignored `.env` only when the file does not already exist.
It provisions only the new `oscar-knowledge` Compose project.

```powershell
cd C:\Users\User\study-workspace\OSCAR\oscar-knowledge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e '.[dev]'
.\scripts\setup.ps1
.\.venv\Scripts\knowledgectl.exe doctor
.\.venv\Scripts\knowledgectl.exe query 'subscription pricing' --mode hybrid
.\.venv\Scripts\knowledgectl.exe jobs
.\.venv\Scripts\knowledgectl.exe sources
.\.venv\Scripts\knowledgectl.exe eval fixtures/eval_questions.json
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8010 --no-access-log --limit-concurrency 32
```

In a second PowerShell window:

```powershell
cd C:\Users\User\study-workspace\OSCAR\oscar-knowledge
.\.venv\Scripts\python.exe scripts/smoke.py
.\scripts\test.ps1 -q
.\.venv\Scripts\ruff.exe check app tests scripts migrations
.\.venv\Scripts\ruff.exe format --check app tests scripts migrations
.\.venv\Scripts\mypy.exe app
```

`test.ps1` temporarily configures test environment variables, restores them on exit, and runs explicit
migrations against port 43115, database `knowledge_test`. Integration fixtures
refuse any database name not ending in `_test`. Do not change these to an OSCAR DB.
Tests use no paid APIs. Unit/contract tests alone: `pytest tests/unit tests/contract`.

## Docker workflow

Use `scripts/setup.ps1` to provision `.env`, or copy `.env.example` to `.env` and
set `KNOWLEDGE_SERVICE_TOKEN` to a freshly generated random value. The sample DB
password is exclusively for loopback local development; use distinct secrets in deployment.

```powershell
docker compose up -d --wait postgres
docker compose --profile app build api
docker compose --profile app run --rm api alembic upgrade head
docker compose --profile app run --rm api knowledgectl doctor
docker compose --profile app run --rm api knowledgectl import-manifest fixtures/demo.yaml
docker compose --profile app up -d --wait api
docker compose --profile app run --rm api knowledgectl query 'subscription pricing'
docker compose --profile worker run --rm worker
```

The worker is a bounded, one-shot job consumer; invoke it again for further batches
or use an operator scheduler. Queue using `--queue-only` during import. Keep queue
creation and processing in the same filesystem environment: Windows absolute paths
are not Docker paths. Container imports must use `/app/data` or packaged fixtures.
Never run `down -v` to repair an installation. No OSCAR Compose files are changed.

## API example

OpenAPI: `http://127.0.0.1:8010/docs`. Mutations are CLI-only. Readiness checks DB,
explicit migration version, vector extension and service token; liveness is minimal.

```powershell
$knowledgeLine = Get-Content .env | Where-Object { $_ -like 'KNOWLEDGE_SERVICE_TOKEN=*' }
$knowledgeHeaders = @{ Authorization = 'Bearer ' + $knowledgeLine.Substring('KNOWLEDGE_SERVICE_TOKEN='.Length) }
$knowledgeBody = @{ query = 'subscription pricing'; collection_ids = @('mba-business'); top_k = 4; mode = 'hybrid' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8010/internal/v1/retrieve -Method Post -Headers $knowledgeHeaders -ContentType application/json -Body $knowledgeBody
```

See [verified-evidence.json](docs/verified-evidence.json) for actual evidence from
the local synthetic corpus. UUIDs depend on the first import; subsequent unchanged
imports preserve chunk IDs. `example.org` URLs in these fixtures identify synthetic
provenance and are **not actual hosted course materials**. The fixture license is
CC0; the code is not assigned a new license by that dedication.

Filters accept `subject`, `course`, `document_ids`, and `publication_year` arrays.
Collection IDs are public slugs, restricted by the configured service allowlist.
Query limit 4,000 chars; top-k 1–20; request body 32 KiB; candidate pool ≤100 per
retrieval path; per-document diversity cap 3. Scores are ranks/similarities, never
probabilities. Keyword search needs no model. Disabled embeddings or a provider
failure make hybrid return `retrieval_mode_used: keyword` with `fallback_reason`.
Explicit semantic requests return 503 when the provider is disabled/unavailable.
Local Ollama needs no embedding API key; explicitly selected OpenAI requires one.

## OSCAR demo

Follow [OSCAR_INTEGRATION.md](docs/OSCAR_INTEGRATION.md). Enable the backend flag
and turn on **Course knowledge** in the chat composer. Ask:

> How should Rentify test its subscription pricing, using the synthetic course notes?

Expect a citation to **Pricing experiments**, course **DEMO-PRICING**, section
**Pricing experiments**. These are deliberately original notes, not MIT content.
Disable/stop the supplementary service and verify workspace chat still responds
with a supplementary-unavailable notice for opted-in turns.

Further details: [architecture](docs/architecture.md), [ingestion](docs/INGESTION.md),
[security](docs/SECURITY.md), [evaluation](docs/EVALUATION.md), and
[verification / changed files](docs/IMPLEMENTATION_REPORT.md).
