# OSCAR Knowledge

An independent evidence-retrieval service for OSCAR. It ingests approved
reference material, preserves source provenance, and returns relevant passages
to the main application. Answer generation remains in the OSCAR backend.

Built with **Python 3.12+, FastAPI, SQLAlchemy, Alembic, PostgreSQL 17, and
pgvector**. Local operation has been verified with Python 3.13.

## Repository responsibilities

| Repository                                                          | Responsibility                                                                          |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **oscar-knowledge**                                                 | Reference ingestion, private library access, embeddings, retrieval, and source metadata |
| [oscar-backend](https://github.com/mengchheanglong/oscar-backend)   | User authentication, project context, memory, answer generation, and orchestration      |
| [oscar-frontend](https://github.com/mengchheanglong/oscar-frontend) | Chat, source previews, reference controls, and review interface                         |

This service owns its database, migrations, and Compose project. It does not own
OSCAR tasks, project records, chat attachments, or personal-memory writes.

## Capabilities

- Approved manifest imports and private-library preparation with explicit
  document revisions and active generations.
- Text extraction, bounded passage preparation, resumable jobs, and embedding
  identities that separate incompatible model generations.
- Keyword, semantic, and hybrid retrieval with bounded candidate pools and
  per-document diversity limits.
- Curated shared collections, owner-scoped private references, and explicit
  exact-book reader grants.
- Citation metadata including document identity, source title, section, physical
  PDF page, edition, extraction method, and coverage notices where available.
- CLI administration, database/runtime diagnostics, and evaluation tooling.

The repository includes synthetic demo fixtures. Private libraries, downloaded
materials, model weights, and installation-specific reports are not shipped with
a fresh checkout. Processing coverage, retrieval relevance, citation integrity,
and factual answer quality are separate measurements.

## Local development

### Requirements

- Python **3.12 or later**; examples use the Windows Python 3.13 launcher.
- Docker with Compose v2.
- Ollama only when local embeddings are explicitly enabled.
- Node.js/pnpm only when also running the main OSCAR application.

Run from this repository. The setup script preserves an existing `.env`; for a
fresh installation it copies the template and generates a random service token.
It starts this service's PostgreSQL, applies migrations, checks readiness, and
imports the bundled synthetic demo.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e '.[dev]'
.\scripts\setup.ps1
.\.venv\Scripts\knowledgectl.exe doctor
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8010 --no-access-log --limit-concurrency 32
```

The PostgreSQL data belongs to this service. Never substitute the main OSCAR
database URL or reset an existing database during setup.

### Local endpoints

| Component                | Endpoint / port              |
| ------------------------ | ---------------------------- |
| Knowledge API            | `http://127.0.0.1:8010`      |
| API documentation        | `http://127.0.0.1:8010/docs` |
| Knowledge PostgreSQL     | `127.0.0.1:43114`            |
| Isolated test PostgreSQL | `127.0.0.1:43115`            |
| Optional local Ollama    | `http://127.0.0.1:11434`     |

`/health/live` is a minimal liveness check. `/health/ready` verifies database
access, migration version, pgvector, and a nonempty service token. Use
`knowledgectl doctor` to check the configured embedding runtime as well.

## Configuration and embeddings

See [.env.example](.env.example) for the full inventory. Keep secrets in ignored
`.env` files or the deployment's secret manager.

| Variable                                  | Purpose / default                                     |
| ----------------------------------------- | ----------------------------------------------------- |
| `KNOWLEDGE_DATABASE_URL`                  | Independent Knowledge database connection             |
| `KNOWLEDGE_SERVICE_TOKEN`                 | Required internal bearer token; empty fails closed    |
| `KNOWLEDGE_ALLOWED_COLLECTIONS`           | Allowlisted shared collection slugs                   |
| `KNOWLEDGE_PRIVATE_SCOPE_SECRET`          | Separate backend-only signing key for private scope   |
| `KNOWLEDGE_PRIVATE_READER_GRANTS_PATH`    | Optional private manifest of exact-book reader grants |
| `KNOWLEDGE_EMBEDDING_PROVIDER`            | `disabled` in the checked-in template                 |
| `KNOWLEDGE_DATABASE_STATEMENT_TIMEOUT_MS` | Bounded SQL timeout; default 5000 ms                  |

Keyword retrieval works without model credentials. Select local embeddings
independently of the main backend:

```dotenv
KNOWLEDGE_EMBEDDING_PROVIDER=ollama
KNOWLEDGE_EMBEDDING_MODEL=qwen3-embedding:0.6b
KNOWLEDGE_EMBEDDING_DIMENSIONS=1024
KNOWLEDGE_OLLAMA_BASE_URL=http://127.0.0.1:11434
KNOWLEDGE_EMBEDDING_MODEL_REVISION=<full-installed-model-digest>
```

Install and warm the model before ingestion. Follow [local Qwen operation](docs/LOCAL_QWEN.md)
for digest pinning, query instructions, endpoint identity, and re-embedding.
Weights are not downloaded automatically. OpenAI embeddings are an explicit
alternative using a separate credential; DeepSeek generation keys are not used
here. Provider selection never falls back automatically to a paid API.

With disabled or unavailable embeddings, hybrid retrieval reports keyword mode
and a fallback reason. Explicit semantic retrieval returns an unavailable error
when no compatible provider is usable. Preserve existing vectors and source
revisions when changing configuration.

## Ingestion and administration

Examples for the bundled synthetic corpus:

```powershell
.\.venv\Scripts\knowledgectl.exe import-manifest fixtures/demo.yaml
.\.venv\Scripts\knowledgectl.exe sources
.\.venv\Scripts\knowledgectl.exe jobs
.\.venv\Scripts\knowledgectl.exe query 'subscription pricing' --mode hybrid
.\.venv\Scripts\knowledgectl.exe eval fixtures/eval_questions.json
```

Use `--queue-only` when staging imports without immediate processing. The worker
is a bounded, one-shot consumer:

```powershell
.\.venv\Scripts\knowledgectl.exe worker
```

Invoke it for further batches or schedule it deliberately. Create and consume
jobs in the same filesystem environment: Windows paths do not become valid
container paths. Administrative mutations are CLI-only. Preserve originals,
source approval, licenses, ownership, and revision provenance. See the
[ingestion guide](docs/INGESTION.md) for supported workflows and limits.

## Connecting OSCAR

The HTTP surface is an internal evidence API:

| Endpoint                                | Purpose                                           |
| --------------------------------------- | ------------------------------------------------- |
| `POST /internal/v1/retrieve`            | Return permitted passages and citation metadata   |
| `GET /internal/v1/collections`          | List allowlisted curated shared collections       |
| `POST /internal/v1/library/collections` | Return authenticated private-library availability |

All internal routes require the service bearer token. Private requests also need
an authenticated-user scope signed by the OSCAR backend, bound to the request
body and a short validity period. A service token alone cannot read private
books. Reader grants apply only to specified books and readers; they do not make
material public or automatically include future imports.

Configure the backend's `OSCAR_KNOWLEDGE_*` settings using its
[integration guide](https://github.com/mengchheanglong/oscar-backend/blob/main/docs/operations/KNOWLEDGE_LOCAL.md).
OSCAR combines this evidence with permitted project context. Its optional
**Knowledge** control or required-source policy is owned by the main application.
The frontend does not connect to this API directly.

## Docker operation

Prepare `.env` with a nonempty random service token before running the API:

```powershell
docker compose up -d --wait postgres
docker compose --profile app build api
docker compose --profile app run --rm api alembic upgrade head
docker compose --profile app run --rm api knowledgectl doctor
docker compose --profile app up -d --wait api
```

For container imports, use packaged fixtures or paths beneath mounted
`/app/data`. The worker profile mounts `./data` there:

```powershell
docker compose --profile worker run --rm worker
```

Host/container Ollama origins are configured separately; the container default
uses `host.docker.internal`. Keep Knowledge and OSCAR Compose projects separate.
Never use `docker compose down -v` as a repair step.

## Verification

The PowerShell runner configures the dedicated `knowledge_test` database on port
43115, runs migrations, and restores previous environment variables afterward.
Tests must never target the main or private-library database.

```powershell
.\scripts\test.ps1 -q
.\.venv\Scripts\ruff.exe check app tests scripts migrations
.\.venv\Scripts\ruff.exe format --check app tests scripts migrations
.\.venv\Scripts\mypy.exe app
```

For unit and contract checks without the integration database:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/contract
```

Deterministic tests do not need paid provider calls. Local-model, real-source,
and cross-service checks have separate prerequisites. Evaluate source identity,
reviewed relevance labels, and answer grounding separately; retrieval scores and
valid citations are not factual-accuracy percentages.

See [focused source retrieval](docs/FOCUSED_SOURCE_RETRIEVAL.md) for the current
named-book recovery behavior, access boundaries and bounded app-evaluation results.

## Quality, access, and deployment boundaries

PDF processing does not guarantee complete understanding of diagrams, equations,
OCR text, or abridged sources. Preserve extraction and coverage notices in any
consumer. Reports document bounded source reviews; a full page-content cleaning
pass remains deferred in the saved handoff.

Private PDFs and local paths are not exposed as a public download library.
Approving ingestion does not grant redistribution or commercial-use rights.
Keep attribution, licenses, and usage restrictions with imported material.
The CC0 dedication for synthetic fixtures does not license the application code
or third-party sources.

Local Compose uses loopback bindings and development-only database credentials.
Public deployment requires private ingress or TLS, dedicated roles, secret
rotation, backups, resource limits, and an operator-reviewed retention policy.
Soft deletion and historical revisions are not immediate physical removal from
storage or backups.

## Documentation

- [Permissioned original passage windows (Phase 3)](docs/PASSAGE_WINDOWS.md)

- [Bounded search and independent retrieval channels](docs/RETRIEVAL_RELIABILITY.md)

- [Topic graph, build command, rollback, and evaluation limits](docs/KNOWLEDGE_GRAPH.md)

- [Architecture](docs/architecture.md) and [OSCAR integration](docs/OSCAR_INTEGRATION.md)
- [Private library integration and reader grants](docs/LOCAL_KNOWLEDGE_LIBRARY_INTEGRATION.md)
- [Local Qwen operation](docs/LOCAL_QWEN.md)
- [Library processing coverage](docs/LIBRARY_COMPLETION_2026_10_26.md)
- [Source review completion](docs/SOURCE_REVIEW_COMPLETION_2026_10_26.md)
- [Content-quality remediation](docs/CONTENT_QUALITY_REMEDIATION.md)
- [Deferred page-content cleaning](docs/NEXT_PDF_CLEANING_PASS.md)
- [Evaluation methodology](docs/EVALUATION.md)
- [Corrective quality-pilot boundaries](docs/QUALITY_PILOT_CORRECTIONS.md)

Active development uses `main`. Keep credentials, private manifests, source
materials, model weights, backups, and installation-specific reports out of Git.
