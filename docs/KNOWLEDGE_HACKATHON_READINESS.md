# OSCAR Knowledge hackathon readiness — 2026-10-25

**Assessment: READY WITH LIMITATIONS for a supervised, noncommercial local demo.**
Real MIT material is indexed with local Qwen vectors. Current-source citations
work through OSCAR and its browser composer. Full production readiness and
universally grounded answers are not established: finance/growth follow-ups still
omitted current citations, and unanswerable retrieval needs a support/abstention
strategy. Use the reviewed scenarios below and inspect the sources live.

## A. Repository Status

Subsequent user workflow direction: **use main directly for all OSCAR repositories**.
The Knowledge validation changes below were fast-forwarded onto main after the
original verification, and AGENTS.md now records that workflow. The table is the
historical validation snapshot, not a requirement to keep using develop.

Verification snapshot before this task's final local commits:

| Repository | Branch | Starting commit | Changes in this task |
| --- | --- | --- | --- |
| oscar-knowledge | develop | be54e22 | Passage evaluation, explicit collection creation, checksum-pinned imports/cache, measured RRF adjustment, startup/readiness/review scripts, tests, corpus metadata and reports |
| oscar-backend | main | 82bbe93 | Historical citation scope, current-turn citation instruction, optional smoke isolation, collection-selecting connector, live MBA acceptance script, documentation |
| oscar-frontend | main | 0dac175 | README branch correction only; application source unchanged |

All three were clean and synchronized with remote main at audit time, each one
commit ahead of remote develop. Backend/frontend AGENTS.md expressly select main.
Knowledge has no AGENTS.md, so this brief's develop rule applies there: develop
was fast-forwarded from its old baseline to the existing Qwen main commit before
editing. No develop→main merge, reset, rebase or force-push occurred in this task.
Final coherent changes are committed locally; no push is authorized by this task.
Use `git log -1 --oneline` in each checkout for its final local commit, which also
contains this report or its cross-reference.

Detailed initial findings: [READINESS_AUDIT.md](READINESS_AUDIT.md). The old brief's
claims that Qwen was unpublished and the corpus was only synthetic were stale.
Accepted ADR lookup through OSCAR MCP succeeded and returned none. No task status
was invented. Existing user files and unrelated containers were preserved.

Changed-file inventory:

- Knowledge: `README.md`; `app/cli.py`, `app/evaluation.py`,
  `app/ingestion/manifest.py`, `app/retrieval/hybrid.py`;
  `docs/EVALUATION.md`, `docs/INGESTION.md`, `docs/architecture.md`, this report,
  `docs/READINESS_AUDIT.md`, `docs/MBA_SOURCE_REVIEW.md`,
  `docs/MBA_CORPUS_VERIFICATION.json`, `docs/MBA_OSCAR_VERIFICATION.json`,
  `docs/MBA_RETRIEVAL_EVALUATION.json`, `docs/QWEN_RUNTIME_VERIFICATION.json`;
  `manifests/mba_mit.yaml`, `manifests/mba_retrieval_gold.json`;
  `scripts/hackathon.ps1`, `scripts/readiness.py`, `scripts/review_approved_mba.py`;
  `tests/integration/test_passage_evaluation.py`, `tests/unit/test_cli.py`,
  `tests/unit/test_evaluation.py`, `tests/unit/test_manifest_checksum.py`,
  `tests/unit/test_retrieval_and_security.py`.
- Backend: `README.md`, `PROJECT_IMPLEMENTATION_GUIDE.md`,
  `docs/operations/KNOWLEDGE_LOCAL.md`, `scripts/connect-knowledge-local.cjs`,
  `scripts/verify-mba-demo.cjs`,
  `src/modules/assistant/context/citation-scope.ts`,
  `src/modules/assistant/context/context-assembler.ts`,
  `src/modules/assistant/context/conversation-context.service.ts`,
  `test/unit/citation-scope.spec.ts`, `test/integration/knowledge-smoke.spec.ts`.
- Frontend: `README.md` only.

Private operational changes: the Knowledge allowlist includes the demo collection;
the backend selects it; a scoped approval manifest, raw PDFs, extraction reports
and acceptance transcripts stay ignored. Existing secrets/provider settings were
preserved. No downloaded corpus, model weight, database backup or private Rentify
content is staged.

## B. Local Model Status

- Ollama 0.40.11: `D:\Apps\Ollama\ollama.exe`.
- Weights: `D:\AI\Ollama\models`, model `qwen3-embedding:0.6b`, Q8_0,
  digest `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`.
- Native single/batch calls returned correctly ordered, finite, nonzero
  **1024-dimensional** vectors. Repeated calls left model files unchanged.
- RTX 3050 6GB Laptop GPU, driver 596.49; GPU execution confirmed. No model
  reinstall/download, larger model, OCR runtime or GPU framework was added.
- Windows listener remains `127.0.0.1:11434`. The actual worker container generated
  a real 1024-vector via `http://host.docker.internal:11434` during this task.
- Explicit Ollama provider is selected; embedding API key is empty. No paid or
  remote embedding request was used. DeepSeek generation remains separately
  configured as `deepseek-flash`, unchanged from the existing local installation.
- Existing migration 0002 preserves legacy 1536 vectors and stores model-specific
  rows separately. No new migration was needed. Active-revision, approval,
  identity and collection filtering remain in place.

See [native runtime results](QWEN_RUNTIME_VERIFICATION.json) and
[local Qwen operation](LOCAL_QWEN.md). Small configuration/log/Windows files still
exist on C:. Repositories and databases were not relocated.

## C. Corpus Status

The user explicitly authorized the three exact MIT OCW PDFs in this chat for the
shared **local noncommercial hackathon demonstration**, with original notices,
attribution and CC BY-NC-SA restrictions preserved. Other resources remain
unapproved. Public accessibility was not treated as approval.

| Course | Resource | Physical pages | Active chunks | Status |
| --- | --- | ---: | ---: | --- |
| 15.390 Entrepreneurship | Course Introduction and Objectives & Viable Business Ideas | 38 | 38 | INDEXED, revision 1 |
| 15.902 Strategy | Budget and Aggregate Metrics | 11 | 12 | INDEXED, revision 1 |
| 15.810 Marketing | Marketing Management — Course Introduction | 10 | 11 | INDEXED, revision 1 |

All 61 active chunks have compatible local Qwen embeddings in the dedicated
`mba-mit-demo` collection. This is three real resources across three subjects,
not eight complete MBA courses. Financial strategy is partly covered in 15.902;
a dedicated finance/economics lecture is not approved or ingested.

[MBA_SOURCE_REVIEW.md](MBA_SOURCE_REVIEW.md) records exact original URLs,
instructors, licenses, all eight inspected course indexes, skipped resources and
extraction issues. [MBA_CORPUS_VERIFICATION.json](MBA_CORPUS_VERIFICATION.json)
records actual document IDs, SHA256 hashes, statuses, revisions and chunk counts.
The reusable manifest remains unapproved; the actual approval manifest is the
ignored `data/mba_courses.yaml`. Raw PDFs, page text, images and private project
content are excluded from Git.

All 59 PDF pages produced nonempty text; original page boundaries are retained.
Five selected Poppler images were visually inspected, alongside instructional
page text. Tables on strategy pp3/10/11 lose relationships in plain extraction;
marketing p2 interleaves columns and p5 is mostly syllabus logistics. These
issues are flagged in stored usage notes. No diagram comprehension or exhaustive
visual QA is claimed. Re-importing all three returned UNCHANGED; hashes, IDs,
revision 1 and vector rows stayed stable.

The old synthetic collection remains intact. Private Rentify records were used
only through normal permissioned OSCAR context, never imported into the shared
curated corpus. Before ingestion the Knowledge DB was backed up to
`D:\AI\Ollama\backups\knowledge-before-mba.dump`.

## D. Retrieval Evaluation

Dataset: [20 source-reviewed questions](../manifests/mba_retrieval_gold.json),
17 answerable, 3 deliberately unanswerable, 18 passage judgments. Labels pin
source hashes, physical pages and text anchors. The coding agent checked source
text and relevant page images; labels were not generated from Qwen rankings.
They have not been independently adjudicated by a human subject expert.

Three initial labels were too narrow: a diagram on marketing p4 and a list on p6
both answer the framework questions. v2 accepts both independently inspected
pages. The following baseline and adjusted results use that same v2 gold set.

| Mode | Hit@5 | Recall@5 | MRR@5 | Mean / p95 latency | Locator accuracy |
| --- | ---: | ---: | ---: | --- | ---: |
| Keyword | 0.7059 | 0.6765 | 0.3471 | 8 / 16 ms | 1.0000 |
| Semantic | 1.0000 | 0.9706 | 1.0000 | 569 / 767 ms | 1.0000 |
| Hybrid, equal-weight baseline | 1.0000 | 0.9706 | 0.7941 | 364 / 414 ms | 1.0000 |
| Hybrid, adjusted broad-keyword weight | 1.0000 | 0.9706 | 0.9412 | 354 / 410 ms | 1.0000 |

Hit/recall/MRR apply to the **17 answerable questions**. Locator accuracy compares
returned document/revision/page/URL metadata against indexed source rows; it does
not mean every returned passage supports a generated claim. No evaluation
request fell back from its requested mode. Measurements include normal host
load and are not isolated microbenchmarks.

Observed weakness: OR-broadened keyword searches promoted broad syllabus/table
matches above stronger semantic matches. Hybrid keeps RRF but weights that
weaker lexical pool at 0.5; original FTS matches retain weight 1. Semantic remains
weight 1. Keyword-only behavior and bounds are unchanged. A regression test
covers the weighting/deduplication. This is an exploratory adjustment on a small
dataset, not held-out proof of general improvement.

Correct example: the limited-resources question retrieves 15.390 p9, with the
actual source URL and page. Remaining failure: the cross-disciplinary question
retrieves a relevant marketing passage but misses one specifically labeled
stakeholder passage in its top five, yielding partial passage recall.

Unanswerable false-positive retrieval: keyword **2/3**, semantic **3/3**, hybrid
**3/3**. Exact company revenue, actual CAC/churn and deployment commands are not
in these lectures. Top-k nearest-neighbor retrieval alone does not abstain. No
uncalibrated threshold was introduced to hide this result. Other answerable
queries' nongold candidates are unjudged, not automatically labeled false.

Full results, rankings and failures:
[MBA_RETRIEVAL_EVALUATION.json](MBA_RETRIEVAL_EVALUATION.json).

```powershell
.\.venv\Scripts\knowledgectl.exe eval-passages manifests/mba_retrieval_gold.json --mode keyword --output data/evaluations/mba-keyword.json
.\.venv\Scripts\knowledgectl.exe eval-passages manifests/mba_retrieval_gold.json --mode semantic --output data/evaluations/mba-semantic.json
.\.venv\Scripts\knowledgectl.exe eval-passages manifests/mba_retrieval_gold.json --mode hybrid --output data/evaluations/mba-hybrid.json
```

## E. OSCAR Integration

The existing internal client still enforces bearer auth, configured destination,
collection allowlisting, four-result/100 KB limits, schema validation and bounded
timeouts. Workspace/project permissions remain enforced. Unit/contract tests
cover invalid scopes, malicious links, malformed/oversized responses, timeouts,
unknown citations and unapproved/deleted sources. The external destination cannot
be set by a chat request. OpenAPI generation produced no contract diff.

The real existing Rentify project was available through the configured OSCAR
account. The older synthetic acceptance PAT could access only AIW; verification
used the already authorized account credential transiently, without changing
memberships or broadening that PAT. Credentials and private answer transcripts
are not in this report or Git.

Live generation used actual Qwen retrieval, existing project context and the
configured DeepSeek provider. Final sequence:

- Business model: three current MIT citations, entrepreneurship and marketing.
- Pricing: two current MIT citations; experiment procedure clearly labeled a
  recommendation because the introductory slides do not teach that protocol.
- Strategy: one current MIT citation for focused opportunity selection; detailed
  platform-defensibility mechanisms were explicitly not established by current
  excerpts.
- Finance and cross-disciplinary growth: live answers completed but omitted
  current MIT citations. They are **limited, not accepted as fully grounded**.
  Some course concepts match the raw PDFs, but uncited carryover from history is
  not sufficient evidence for the present reply.

Initial live review found historical evidence-number reuse. Generation context
now strips old markers from prior dialogue/recall/summary messages while retaining
their text, saved history, the current user request and current evidence table.
The system explicitly scopes numbering to the current turn. Tests verify this
boundary. It mitigates wrong-number rebinding; it is not a semantic fact checker.
Failed/limited acceptance conversations were preserved, not rewritten as passes.

A further **actual frontend composer** turn, with Course Knowledge checked,
produced a two-sentence answer about focused opportunity selection, citing
15.390 **physical page 9** and distinguishing the general principle from proven
Rentify demand. The browser inspector showed MIT, 15.390, revision 1, Page 9,
the actual excerpt and the verified original PDF link. Source cards work with
stored evidence numbers, including numbers that follow project evidence.

With the Knowledge API container actually stopped, a live opted-in turn displayed
the unavailable notice and no external citations; a normal opted-out turn also
completed. Authenticated tasks, goals, MAVIS listing and project keyword search
returned successfully during that outage. The API was restarted and readiness
rechecked. No automatic MAVIS memory write was requested or performed.

Sanitized results: [MBA_OSCAR_VERIFICATION.json](MBA_OSCAR_VERIFICATION.json).
The full private transcript, source metadata and conversation URL are in backend
`var/mba-demo/latest.json`. Browser screenshots remain private under
`D:\AI\Ollama\logs\hackathon`.

## F. Test Results

| Repository / check | Actual final result |
| --- | --- |
| Knowledge `KNOWLEDGE_TEST_LOCAL_MODEL=1; scripts/test.ps1 -q` | **72 passed**, 0 failed, 0 skipped; 6 dependency deprecation warnings; 32.70 s |
| Knowledge Ruff lint / format / mypy | Passed; 47 Python files formatted, 26 application files typed |
| Backend unit `pnpm test` | **436 passed**, 54 suites |
| Backend E2E `pnpm test:e2e` | **173 passed**, 14 suites |
| Backend `OSCAR_KNOWLEDGE_SMOKE=true; pnpm test:integration` | **143 passed**, 17 suites, 0 skipped; includes real Knowledge HTTP with scripted generation for that one deterministic test |
| Backend lint / typecheck / build | Passed |
| Backend OpenAPI generation | Passed; tracked contract unchanged |
| Backend formatting | Passed after formatting the new operational script |
| Frontend lint / typecheck / tests | Passed; **34 tests**, 0 failed/skipped |
| Frontend production build | Passed in an isolated same-volume copy of the actual tracked source with existing dependencies; running dev output preserved |
| Live model / API / worker / browser / outage | Executed against actual components; limits and partial grounding recorded above |

Knowledge tests use the separate `knowledge_test` DB on 43115. Backend integration
creates/removes only a generated `*_test` DB on its test server 43105. No test
database was pointed at development data. Test HTTP is blocked except explicit
local model opt-in; no paid embedding transport is used. Live DeepSeek checks
are explicitly separate from mocked generation tests.

Failures found and resolved: initial optional smoke fixture leakage caused five
history tests to see unrelated generated messages; the smoke now cleans only
its own test records and writes its artifact privately. Its test-specific timeout
is explicit to tolerate concurrent host validation; production remains 2500 ms.
The first isolated frontend build failed due to a cross-drive dependency junction;
the same source built successfully using a same-C:-volume validation copy. New
CLI evaluation initially exposed unsupported Literal options in the installed
Typer; validated string choices fixed that before final tests. These failed
attempts are not counted as passes. Final logs are under
`D:\AI\Ollama\logs\hackathon`.

## G. Performance

| Sample | Measurement |
| --- | --- |
| Model download | 639,150,858 bytes (~610 MiB), unchanged during inference |
| Warm native single request | 119 ms; first measured request 144 ms was also warm |
| Native batch 2 / 16 | 261 / 451 ms; ~35.5 short embeddings/second for batch 16 |
| Initial real PDF ingestion | 15.390: 3.02 s; 15.902: 2.59 s; 15.810: 2.29 s, from durable job timestamps |
| Adjusted hybrid retrieval | Mean 354 ms, p95 410 ms on the 20-question sample |
| Final live scenario generation | Approximately 4.2–5.7 s per answer, including normal orchestration |
| GPU memory | Approximately 1.2 GB model allocation; GPU total observed ~1267 MiB of 6144 MiB |

CPU fallback and cold-start latency were not benchmarked anew. The prior install
recorded a load exceeding 50 seconds; startup explicitly warms the model with a
180-second timeout and keeps it resident. Unloading/restarting can exceed query
budgets until warmed. Limits remain 256 embedded chunks/document, batch 16 (max
32), one ingestion worker recommended, 100,000 model-vector rows and exact cosine
ranking. The small sample does not establish throughput at corpus scale.

## H. Hackathon Demo

From the Knowledge repository, the verified existing-machine startup is:

```powershell
cd C:\Users\User\study-workspace\OSCAR\oscar-knowledge
.\scripts\hackathon.ps1 -Start
.\scripts\hackathon.ps1
```

It starts/waits for the D: Ollama tray app, warms Qwen, starts the Knowledge DB,
explicitly checks/upgrades its migrations, builds/starts its API, then invokes the
existing OSCAR startup script with optional external agents skipped. It does not
reset databases, seed records, stop unrelated processes or overwrite secrets.
The read-only readiness check verified every component READY, model AVAILABLE,
three approved documents, 61 compatible vectors and HYBRID mode without fallback.
User logon starts Ollama on this machine; restart registration was not tested by
rebooting Windows.

For a newly configured approved local collection, set the private Knowledge
allowlist to include `mba-mit-demo` alongside the existing collection, then:

```powershell
.\.venv\Scripts\knowledgectl.exe create-collection mba-mit-demo 'MIT OCW noncommercial local demo'
.\.venv\Scripts\knowledgectl.exe import-manifest data/mba_courses.yaml
.\.venv\Scripts\knowledgectl.exe doctor
.\.venv\Scripts\knowledgectl.exe query 'Why focus on one opportunity with limited resources?' --collection mba-mit-demo --mode hybrid
cd ..\oscar-backend
node scripts/connect-knowledge-local.cjs --collection mba-mit-demo
# Restart the local backend only if its environment changed.
```

The ignored manifest must carry the actual curator approval and pinned hashes;
the reusable discovered manifest does not authorize import. Run ingestion on
Windows for these Windows file paths. A container worker can re-embed stored
chunks; source parsing must use paths mounted/available in that worker environment.

Open OSCAR on `http://127.0.0.1:43100`, select Rentify, and enable **Course knowledge**.
Start with the verified focused question:

> Using the MIT New Enterprises lecture, explain why a startup should focus on
> one opportunity when resources are limited. Distinguish that principle from a
> claim that Rentify has proven demand. Cite the current course evidence in two
> short sentences.

Expected support: **15.390, Page 9**. Inspect the source card and original PDF.
Then use the business-model, pricing and strategy prompts in
`scripts/verify-mba-demo.cjs`. The full broad business question should distinguish
source principles from company hypotheses and admit missing detailed finance or
defensibility support. Do not promise that every follow-up is fully grounded.
The private acceptance script requires normal access to the existing RENTIFY
project; the older AIW-only test PAT cannot access it. `--live` makes real model
calls; `--resume` continues incomplete checks; `--offline` requires the Knowledge
API stopped and is a separate live outage test. Tokens are supplied privately.

Recovery:

- Ollama unavailable: start `D:\Apps\Ollama\ollama app.exe`, run
  `scripts/warmup-ollama.ps1`, check `ollama ps` and `nvidia-smi`. GPU fallback
  should be reported honestly; no new GPU framework is required.
- Knowledge DB unavailable: start only its Compose postgres service, check health
  and `alembic current/upgrade head`. Preserve the volume and backups.
- Failed job: inspect `knowledgectl jobs`; correct the source/config, then run a
  bounded Windows `worker --retry-failed --limit 20`. Old active revisions remain.
- Missing vectors: `reembed --collection mba-mit-demo`, then doctor/readiness.
- Internal auth/destination problem: `node scripts/connect-knowledge-local.cjs
  --collection mba-mit-demo --check`; inspect local URLs and restart only the
  relevant process. Never print tokens.
- Chat timeout: warm Qwen and check real hybrid latency. Keep Course Knowledge
  optional; the API outage test verified normal chat survives.

## I. Outstanding Work

1. **Before unrestricted answer-quality claims:** independently review passage
   judgments, expand held-out/unanswerable tests and establish answer-support
   checks/abstention. Current nearest-neighbor false-positive rate is high.
2. **Before presenting finance/growth as grounded:** obtain suitable approved
   finance/economics material and verify current-turn citations in those answers.
   Historical citation-number scoping mitigates one defect, not all LLM errors.
3. **Before numeric table claims:** inspect original pages or improve structured
   extraction. Current metadata flags do not restore table relationships.
4. **Before broader sharing/commercial deployment:** review rights and third-party
   exceptions, operational security, backups, access policies and production
   hosting separately. This is an explicitly limited local MIT demo.
5. Deferred: larger corpus/load tests, ANN, OCR, video/transcription, rerankers,
   GraphRAG, distributed systems and MAVIS migration. None was introduced.

## J. Final Readiness Assessment

**READY WITH LIMITATIONS.** The required local chain is demonstrated with genuine
approved source material, real GPU embeddings, pgvector, semantic/hybrid ranking,
normal OSCAR authentication/project context, live DeepSeek generation and an
actual browser-composer answer with a verified MIT page citation. Startup,
regressions and actual service-outage degradation were exercised successfully.

The supported claim is a supervised noncommercial hackathon demonstration. Two
follow-up scenarios are not fully cited, unanswerable search does not abstain,
and only a small introductory corpus is approved. Those findings prevent a
general production-ready or universally accurate RAG claim.
