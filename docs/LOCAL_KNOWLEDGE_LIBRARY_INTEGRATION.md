# Local knowledge library integration

Verified locally on 2026-10-25. Work is on `main` in all three OSCAR repositories.
Original PDFs remain in `D:\AI\OSCAR\Knowledge`; the separate existing
`D:\AI\OSCAR\mba-corpus` remains authoritative for its own files. No source was
moved, renamed, deleted or edited. The local reports and source content are not
Git artifacts.

## Current outcome and limits

- Catalog: 25,051 physical supported resources across both roots, plus two logical
  book ranges referencing the original compilation without copying it.
- New private library: 487 retrievable references (74 PDF references and 413 HTML
  sections), 4,594 active document parts, 43,859 active chunks and matching current
  Qwen vector rows. `personal-library` has 30 references; `social-systems` has 457.
- PDF preparation spans 29,948 physical pages, including blanks and excluded
  unreadable pages. Local English OCR produced text on 466 pages. Seven references
  are explicitly partial; nine unresolved pages are excluded from evidence.
- All 43 Social Systems roadmap readings have retrievable reference matches.
  This is title/resource coverage, not proof of complete matching editions or an
  accredited curriculum. Some existing PDFs are summaries; publication year and
  edition remain unknown unless verified.
- The 156,324-page, approximately 1.7 GiB compilation is authorized and cataloged,
  but only its two verified roadmap ranges (2,446 pages) were indexed. The other
  209 outline candidates remain unindexed. An outline candidate is not a verified
  unique edition. This remaining work is technical, not awaiting user permission.
- Existing 1,384 documents, 36,790 chunks and 36,797 vector rows passed an ID,
  revision/content and vector-hash comparison with the pre-library baseline.
  The shared `mba-majors` import remains 1,374 documents and 36,722 active chunks.

Detailed local evidence lives under
`D:\AI\OSCAR\Knowledge\Catalog\reports`: `INGESTION_REPORT.md`,
`RETRIEVAL_EVALUATION.md`, `SECURITY_REVIEW.md`, `extraction-audit.json`,
`original-file-audit.json`, and `preservation-audit.json`. The canonical catalog
and roadmap CSV include per-resource partial coverage and unresolved pages.

## Catalog and physical organization

`Catalog\library.json` is the single metadata authority. UUID resource identities
persist across a uniquely identifiable move within the scanned roots. Separate
copies keep separate resource and permission identities. File changes retain the
logical resource ID, invalidate checksum-bound permission review and stage a new
generation; active old evidence remains until explicit revocation or complete
replacement. A missing file is recorded without deleting history or vectors.

Entries include root/relative/absolute path, size, modification time, SHA-256,
format, sampled extraction classification, PDF page count, title/author metadata,
review status, category/tags, collection, explicit rights, owner/visibility and a
derived ingestion snapshot. Filename/embedded metadata is unverified by default;
edition, year and ISBN are not guessed. Catalog paths stay local and never become
API citation URLs. `virtual_books` contains bounded physical-page references to
the same original PDF, with explicit range evidence.

The seven numbered directories are subject categories within `personal-library`.
The existing `Social Systems` hierarchy maps to private `social-systems`.
`Knowledge\MBA` is currently empty. The shared curated MBA corpus remains separate.
Generated `duplicates.json`, `rename-plan.json` and reports are views, not competing
authorities. SHA duplicates and possible title/edition matches are separate. No
automatic merging, canonical-copy deletion or cross-copy permission transfer is
implemented. Rename proposals require title/author/edition and collision review.

## Authentication and private scope

The ordinary OSCAR session/PAT identifies the user. After normal conversation
authorization, the backend signs the actual user's UUID, audience, short expiry
and exact request-body hash using `OSCAR_KNOWLEDGE_PRIVATE_SCOPE_SECRET`.
Knowledge verifies the matching `KNOWLEDGE_PRIVATE_SCOPE_SECRET` as well as its
existing service bearer. Use an independent random secret of at least 32
characters, different from the service token. Keep both only in private `.env`.

Collection slug alone, client-provided owner fields, or service bearer alone do
not grant private access. SQL filters owner, visibility, approval, active book
generation and active document revision before ranking; returned evidence is
rechecked. Private collection counts require the same authenticated scope and
contain no titles, paths or owner identifiers. Public listing excludes private
collections. New books are private unless a curator explicitly approves a
separate allowlisted shared collection. Ownership does not create a shared or
commercial redistribution grant.

This is a local trusted-host boundary. Filesystem/DB administrators and the
backend signing key remain trusted. It is not machine-admin isolation or a
public-production security certification. The configured chat provider receives
bounded retrieved snippets when the user opts in. Source PDFs are not served by
the API. No embeddings are sent to external providers for private indexing.

## Local operation and adding files

Run native Windows CLI commands from this repository with its existing `.venv`;
the API container need not mount the D: source library. Local Knowledge PostgreSQL
uses port 43114, API 8010, existing Ollama 11434. Backend/frontend use 43101/43100.
Do not point these commands at deployment databases.

```powershell
# Read-only discovery: dry-run writes nothing.
.venv\Scripts\knowledgectl.exe library scan `
  --root D:\AI\OSCAR\Knowledge --root D:\AI\OSCAR\mba-corpus --dry-run

# Update metadata and derived inventory; no automatic ingestion or rename.
.venv\Scripts\knowledgectl.exe library catalog `
  --root D:\AI\OSCAR\Knowledge --root D:\AI\OSCAR\mba-corpus

# Approve one reviewed new source for its authenticated owner's private use.
# Replace placeholders with the catalog resource UUID and actual OSCAR user UUID.
.venv\Scripts\knowledgectl.exe library review RESOURCE_UUID `
  --owner-id OSCAR_USER_UUID --evidence 'Private indexing and assistant use authorized by owner'

# Resumable preparation, at most 100 physical pages per invocation.
# Repeat until complete, then ingest. The original is never rewritten.
.venv\Scripts\knowledgectl.exe library prepare-book RESOURCE_UUID --page-batch 100
.venv\Scripts\knowledgectl.exe library ingest-book RESOURCE_UUID `
  --collection personal-library --limit 100

# Derived status from actual active chunks, with optional original PDF audit.
.venv\Scripts\knowledgectl.exe library sync --verify-originals
```

Strict ingestion refuses unresolved pages. `--allow-partial` is an explicit choice
to publish only recovered text with a persistent coverage notice. Set the
resource's reviewed `ocr_tessdata` to the existing
`D:/AI/OSCAR/tools/tessdata` for local Tesseract English OCR. Never label a partial
reference as fully read. OCR mathematics, formulas, diagrams and tables require
comparison with original physical PDF pages.

For a finite local batch, `scripts/process_owned_library.py --limit 10` processes
approved private resources only; it does not grant permission. Use
`--resource-id RESOURCE_UUID` to target a failed resource or `--allow-partial`
after reviewing unresolved-page coverage. Run `library sync` afterwards.
`scripts/register_owned_library.py` re-applies the existing frozen checksum
approval snapshot and acquisition manifests; it cannot approve newly added or
changed PDF bytes by mere possession. Individual `library review` is the normal
future-file workflow. No permanent watcher or second RAG service was added.

For an oversized compilation, inspect actual outline/page boundaries, then:

```powershell
.venv\Scripts\knowledgectl.exe library register-range PARENT_RESOURCE_UUID `
  --first-page 100 --last-page 300 --title 'Verified book title'
```

Use the returned logical resource UUID with preparation/ingestion. Ranges must
contain at most 2,000 pages and use physical PDF page numbers. Review overlaps and
duplicate editions first. This reads one canonical PDF, not a new PDF copy.

## Bounded extraction, incremental indexing and recovery

Preparation uses child processes, 100-page batches, a 120-second deadline and
observed 512 MiB working-set termination. This sampled memory monitor is not a
hard OS memory reservation. Source limits are 512 MiB (2 GiB for verified ranges),
2,000 pages per logical reference, 100,000 extracted characters per page and
bounded OCR render pixels. Text/HTML/Office preparation is bounded too. Oversized,
encrypted, corrupted or unreadable sources fail explicitly; limits never silently
truncate a full book and label it complete.

Small `.bookpart` JSON envelopes under `Catalog\ingestion-cache` preserve actual
PDF pages and verified outline headings. UTF-8 checkpoints are atomic and
restartable. The `bookparts-v2` cache namespace fixes an early Windows checkpoint
encoding error; an exact embedded-text audit passed after repair. Valid earlier
cache parts remain readable. No PDF, model weights or vector arrays are copied
into the catalog.

Existing chunking/jobs/Qwen/pgvector/RRF are reused. A book generation activates
only after every expected part succeeds and the active chunk count agrees.
Unchanged part text/provenance reuses its original document/chunk IDs and vectors;
changed parts stage new content. Per-book advisory locks serialize ingestion.
Changed preparations and model identities invalidate reuse. The active generation
switch is atomic; stopping a worker retains a usable old generation/checkpoint.
Do not delete old vectors or reset databases to retry. Check safe error codes,
fix the source or configuration, re-review changed bytes, and resume the same ID.

```powershell
# Deny retrieval immediately, retaining files and historical chunks/vectors.
.venv\Scripts\knowledgectl.exe library revoke RESOURCE_UUID
# Re-review using the same owner, then ingest again to activate it explicitly.

# Audit embedded PDF text; mismatches are gated off as REPAIR_REQUIRED.
.venv\Scripts\python.exe scripts/audit_prepared_books.py
# Regenerate local reports; optional baseline verification is read-only.
.venv\Scripts\python.exe scripts/report_library.py `
  --baseline D:\AI\OSCAR\mba-corpus\2026-10-25\private-backups\pre-library-baseline.json
```

The audit intentionally excludes OCR from byte-equivalence comparison. Keep OCR
review warnings even after automated extraction succeeds. Retrieval caches and
private report files must not be published or committed.

## Embeddings, retrieval and citations

The existing local `qwen3-embedding:0.6b` pin and 1,024 dimensions are unchanged.
No duplicate model or vector service was installed. Private keyword queries can
work without embeddings; private semantic/hybrid queries require local Ollama.
Existing explicit hybrid fallback remains visible. Shared embedding settings are
unchanged. Private model migration is not a fully automated CLI workflow yet.

Filters include title/author/source type/subject/course/year/document IDs; SQL
permissions apply independently of filters. Candidate diversity is capped per
logical book. Evidence carries resource/book ID, original source title, known
author/edition, actual physical PDF page, verified outline chapter, revision,
extraction/review notice and partial-coverage notice. No local path is returned.
Unknown printed page labels/chapter titles are not invented. PDF math layouts
can still be lossy even when embedded text is extractable.

The generic shared `knowledgectl query` command intentionally has no private-user
impersonation option. Use authenticated OSCAR or the trusted local evaluation
script for private retrieval. Book content remains reference evidence, separate
from project facts/tasks and MAVIS memory; it cannot authorize actions.

## Backend/frontend setup and use

In the backend, `node scripts/connect-private-library.cjs --check` validates the
ordinary authenticated local account and independent scope keys without printing
credentials. Running without `--check` connects keys only. Its explicit
`--approve-owned-pdfs` option is an operator action to record newly authorized
PDF checksums, not an automatic startup step. The current user's explicit approval
has already been recorded; no repeat approval is needed for these existing bytes.

Open OSCAR at `http://127.0.0.1:43100/assistant`, enable **Reference knowledge**, and
choose **MBA**, **Personal Library**, **Social Systems**, or **All permitted
references**. Default behavior remains opted out, with MBA the default selected
scope. Private counts are references (HTML sections also count), not necessarily
distinct books. Unavailable scopes are disabled. Citations open saved excerpts,
show author/physical page/collection and link public URLs only when valid. Local
books display a catalog-reference label rather than a dead download link.

`GET /api/v1/knowledge/collections` requires ordinary authentication. Chat accepts
optional `knowledgeScope: mba | personal-library | social-systems | all` with
`includeKnowledge: true`; the actual authenticated user is forwarded. Scope is
part of the idempotency fingerprint. Source previews and saved history retain
citations, but do not expose local PDF files.

## Migrations, rollback and validation

Additive migrations `0003_library_books`, `0004_private_library_scope` and
`0005_book_preparation_identity` preserve original records and vectors. Local DB
is at 0005. A pre-library `pg_dump` and row/hash baseline are retained privately in
the existing MBA backup area. No database reset, volume deletion or destructive
downgrade was performed. These migrations refuse destructive downgrade; rollback
means disable private-scope keys and restart the current compatible services while
retaining schema/data/shared settings. Old code may reject the newer schema head;
do not deploy old binaries against it without a compatibility plan.

Actual checks: Knowledge isolated suite 88 passed/1 skipped; backend
440 unit, 173 E2E and 142 isolated integration tests passed, with one optional
real-HTTP integration skipped. Lint/typecheck/build, OpenAPI generation and frontend
34 tests passed. The six-question real retrieval sample returned each expected
book in the top five in keyword, semantic and hybrid modes (hybrid MRR 1.0,
median 0.4284 s). This is a small gold-book sample, not exhaustive answer accuracy.
The 32-passage local embedding probe measured 16.41 passages/s under current load.

Four unique scripted configured-model chat requests checked two private books,
unanswerable abstention and opt-out, plus replay/saved-citation reload and changed
scope conflict. One browser chat cited Thinking in Systems. Authentication and
private scope checks denied bearer-only/expired access, returned no unrelated-user
evidence and zero unrelated-user counts, and excluded private content from shared
queries/listing. These checks verify the integration, not every generated claim.

## Social Systems acquisitions

Missing roadmap texts were filled from official CORE Econ HTML and Project
Gutenberg, while two OpenStax book ranges were identified in the existing owned
compilation. Keep the downloaded original notices, manifest URLs and hashes.
CORE collection covers 412 HTML pages across Doing Economics and Economy 2.0
micro/macro; the additional complete Wealth of Nations HTML supplies the local
Books I–III PDF's missing remainder. Interactive assets/gated answers are excluded.
Two ambiguous old HTML files remain quarantined without deletion.

Sources: [CORE Doing Economics](https://books.core-econ.org/doing-economics/book/text/0-3-contents.html),
[CORE Microeconomics](https://books.core-econ.org/the-economy/microeconomics/0-3-contents.html),
[CORE Macroeconomics](https://books.core-econ.org/the-economy/macroeconomics/0-3-contents.html),
[CORE copyright notice](https://books.core-econ.org/the-economy/microeconomics/0-2-copyright.html),
[Project Gutenberg ebook 3300](https://www.gutenberg.org/ebooks/3300).
No access controls were bypassed. Private indexing approval is not authorization
to republish these materials or remove third-party notices.
