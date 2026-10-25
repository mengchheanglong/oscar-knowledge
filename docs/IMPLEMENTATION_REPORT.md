# Implementation and verification — 2026-10-25

This records the initial implementation. The subsequent local Qwen installation,
additive migration 0002, live inference and latest checks are documented in
[QWEN_IMPLEMENTATION_REPORT.md](QWEN_IMPLEMENTATION_REPORT.md).

Implemented an independent sibling directory `oscar-knowledge`, with its own DB,
explicit Alembic schema, ingestion jobs, parsers, optional embedding provider,
keyword/vector/hybrid evidence retrieval, authenticated HTTP API and CLI. Added
minimal feature-gated OSCAR integration and an opt-in frontend checkbox.
No existing OSCAR tables, migrations, embedding settings, Compose identity,
development records, or unrelated AGENTS.md edits were changed. At the original
implementation handoff, nothing had been committed, pushed or deployed publicly.
OSCAR MCP accepted-decision lookup returned
`fetch failed`; no decision consultation or task completion was fabricated.

## Verification

| Check | Result | Scope |
| --- | --- | --- |
| Python 3.13 environment and pinned dependencies | PASS | Windows install and Linux Docker image |
| Explicit Alembic upgrade | PASS | New knowledge DB and separate knowledge_test DB |
| Knowledge pytest | PASS, 41 tests | Unit, API contract and actual PostgreSQL/pgvector integration; no paid calls |
| Ruff lint / format | PASS | app, tests, scripts, migrations |
| mypy | PASS | 19 application source files |
| Local CLI setup/import/doctor/query/jobs/help | PASS | Six synthetic authorized Markdown fixtures; every command help tested |
| Unchanged imports | PASS | All six return UNCHANGED; DB tests verify stable chunk IDs |
| Docker build and API readiness | PASS | Non-root, read-only API; loopback 8010; separate Compose project |
| Real HTTP retrieval smoke | PASS | Auth rejection, readiness, keyword fallback, locators, natural-language demo query |
| Synthetic evaluation | PASS | 20 questions; Hit@6=1.0, Recall@6=1.0, MRR@6=1.0; fixture-only |
| OSCAR backend unit | PASS, 435 tests | 53 suites, including optional client, fingerprint, citations and outage behavior |
| OSCAR backend end-to-end | PASS, 173 tests | 14 existing suites |
| OSCAR backend DB integration | PASS, 142 tests | 16 suites, isolated generated *_test database |
| Cross-service smoke | PASS, 1 additional test | Real knowledge HTTP + OSCAR PostgreSQL persisted answer/citation; generation transport scripted |
| Backend lint/typecheck/build/format | PASS | OpenAPI regenerated and additive diff inspected |
| Frontend tests | PASS, 33 tests | Includes safe external citation link regression |
| Frontend lint/typecheck/build | PASS | Existing Next.js build; no dependency changes |
| Live paid model / embedding call | NOT RUN | No paid call made; semantic DB tests use synthetic 1536-vectors |
| Actual MIT import / real-source quality / browser interaction | NOT RUN | University entries unapproved; UI was built/typechecked, not interactively exercised |

Initial checks exposed a heading-only chunk, environment-dimension coercion,
CLI Literal compatibility, an evidence-object regression and a test-script
environment leak. These were corrected and relevant checks rerun; earlier failed
attempts are not being counted as passes. PyMuPDF/Starlette emit dependency
deprecation warnings; the tests complete successfully.

See `verified-evidence.json` for actual HTTP evidence. See
`verified-oscar-answer.json` for the answer and citations re-read from OSCAR's
isolated test database. That artifact explicitly labels the scripted DeepSeek
transport. Its intentionally invalid Evidence #99 has no persisted citation;
unknown markers remain unavailable in the existing citation UI.

## Repeat the cross-service check

Start knowledge using the README first. In the backend directory:

```powershell
pnpm db:test:up
$env:OSCAR_KNOWLEDGE_SMOKE = 'true'
pnpm test:integration --testPathPatterns=knowledge-smoke
Remove-Item Env:OSCAR_KNOWLEDGE_SMOKE
```

This test is explicitly skipped during ordinary backend integration runs when
the smoke flag is absent, because it requires the independently running sibling
service and seeded synthetic corpus. The test reads the ignored knowledge `.env`
token without printing it. It never contacts a paid model endpoint: only the local
knowledge HTTP request is real; DeepSeek transport is intercepted. Existing test
runner creates and removes only its own randomly named test database.

## Files changed in existing repositories

Backend paths (relative to `oscar-backend`):

```text
.env.example
PROJECT_IMPLEMENTATION_GUIDE.md
docs/api/openapi.json
src/config/environment.ts
src/modules/knowledge-client/knowledge-client.module.ts
src/modules/knowledge-client/knowledge-client.service.ts
src/modules/knowledge-client/knowledge-evidence.ts
src/modules/assistant/assistant.module.ts
src/modules/assistant/assistant.service.ts
src/modules/assistant/context/context-assembler.ts
src/modules/assistant/dto/chat-message-response.dto.ts
src/modules/assistant/dto/post-message.dto.ts
src/modules/assistant/entities/chat-message.entity.ts
src/modules/assistant/llm/llm-provider.interface.ts
test/unit/assistant.service.spec.ts
test/unit/knowledge-client.spec.ts
test/integration/knowledge-smoke.spec.ts
```

Frontend paths (relative to `oscar-frontend`):

```text
src/app/assistant/page.tsx
src/components/assistant/assistant-composer.tsx
src/lib/api.ts
src/lib/knowledge-citation.ts
test/knowledge-citation.test.cjs
```

## New service files

```text
.dockerignore
.env.example
.gitignore
Dockerfile
README.md
alembic.ini
compose.yaml
pyproject.toml
requirements.lock
app/__init__.py
app/config.py
app/main.py
app/security.py
app/api/__init__.py
app/api/schemas.py
app/db/__init__.py
app/db/models.py
app/db/session.py
app/embeddings/__init__.py
app/embeddings/provider.py
app/ingestion/__init__.py
app/ingestion/chunking.py
app/ingestion/loaders.py
app/ingestion/manifest.py
app/ingestion/pipeline.py
app/retrieval/__init__.py
app/retrieval/hybrid.py
app/cli.py
migrations/env.py
migrations/versions/0001_initial.py
manifests/mba_mit.yaml
fixtures/demo.yaml
fixtures/pricing.md
fixtures/strategy.md
fixtures/entrepreneurship.md
fixtures/economics.md
fixtures/finance.md
fixtures/decisions.md
fixtures/eval_questions.json
scripts/create_fixtures.py
scripts/setup.ps1
scripts/smoke.py
scripts/test.ps1
tests/conftest.py
tests/contract/test_api.py
tests/integration/test_pipeline.py
tests/unit/test_cli.py
tests/unit/test_loaders.py
tests/unit/test_retrieval_and_security.py
docs/architecture.md
docs/INGESTION.md
docs/OSCAR_INTEGRATION.md
docs/SECURITY.md
docs/EVALUATION.md
docs/IMPLEMENTATION_REPORT.md
docs/verified-evidence.json
docs/verified-oscar-answer.json
```

Generated local `.env`, `.venv`, caches, and the separate Docker volume are
excluded from source control. Following the user's repository publication request,
the independent service is prepared for the private GitHub repository
`mengchheanglong/oscar-knowledge` on branch `develop`. Backend and frontend
integration changes listed above remain in their respective local repositories;
they are not included in the independent service repository.

## Remaining limits and deliberate deferrals

- A live OSCAR answer using the real configured model remains a manual acceptance
  step after enabling the documented backend settings and composer opt-in. The
  delivered automated demonstration uses scripted generation, never fake live results.
- Six CC0 synthetic fixtures are indexed. Eight official MIT candidates are
  recorded; three real PDF URLs were verified. Approval and intended-use/license
  review remain explicit curator actions. No MIT corpus is silently imported.
- Exact pgvector baseline only; HNSW enablement and large-corpus plan/recall
  measurement are deferred. No million/billion-chunk throughput claims.
- English FTS only. Natural-language queries broaden to ≤32 indexed OR terms
  when strict matching yields no candidates. Real-source retrieval quality needs
  its own gold evaluation. Long poorly extracted tables are flagged, not repaired.
- Jobs restart from source after a failed/expired lease. Per-batch embedding
  outcomes are recorded, but partial vectors are not reused after a crash.
  Embedding limits are per document/worker, not an account-wide dollar hard cap.
- Worker is bounded and one-shot; no Redis, scheduler, distributed queue, automatic
  infinite retries, private tenancy, public rate-limiting layer or deletion automation.
- OCR, Whisper/transcription, audio/video/DRM downloads, graph RAG, custom model
  training, agents/crawlers, rerankers and legacy RAG replacement are deferred.

Demo question with **Course knowledge** enabled:

> How should Rentify test its subscription pricing, using the synthetic course notes?

Expected source: **Pricing experiments / DEMO-PRICING / Pricing experiments**.
Example.org fixture URLs identify synthetic provenance; they are not hosted
university source pages. For an actual university demo, curate an authorized
lecture resource and repeat ingestion/evaluation before presenting claims.
