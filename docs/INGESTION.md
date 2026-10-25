# Ingestion and provenance

Only authorized **curated shared** documents belong here. Do not import personal
workspace records or MAVIS memory. `--approve` confirms sharing with every OSCAR
user that can opt in to this collection. No permission is inferred from a filename.

```powershell
New-Item -ItemType Directory -Force data/inbox
# Place authorized PDF/DOCX/TXT/MD/HTML/SRT/VTT/CSV/XLSX files here.
.\.venv\Scripts\knowledgectl.exe ingest-dir data/inbox --collection mba-business --approve --queue-only
.\.venv\Scripts\knowledgectl.exe worker --limit 20
.\.venv\Scripts\knowledgectl.exe jobs
.\.venv\Scripts\knowledgectl.exe worker --retry-failed --limit 20
.\.venv\Scripts\knowledgectl.exe reindex --document-id '<UUID from sources>'
.\.venv\Scripts\knowledgectl.exe sources
```

For proper titles, public URLs, institution, subject, licensing and course fields,
copy `fixtures/demo.yaml` into a curator-owned manifest directory and edit entries.
Local files must resolve below that manifest directory. Never put private absolute
paths into title/course/locator fields. Local paths are stored only internally;
neither retrieval responses nor provenance export includes them.

PDF text is extracted per physical PDF page (1-based); printed slide numbers may
differ. Image-only PDFs become `SKIPPED / OCR_REQUIRED`. OCR is deferred.
DOCX paragraphs/headings and tables retain logical order. UTF-8 is required for
text; invalid encoding receives a safe error instead of silently corrupting text.
HTML strips scripts, styles, forms and common navigation elements, with no JS
execution. Subtitle cues retain start/end milliseconds and remove repeated overlap.
CSV/XLSX rows use their header labels and row identity. XLSX is read-only, formulas
are not evaluated; only cached values are read. Google Forms exports can be
ingested as authorized CSV; there is no forms permission bypass or live connector.
No audio/video download or transcription runtime is included.

Chunks target 2,400 characters (roughly 600 estimated tokens), overlap 360
characters (~90 estimated tokens), hard cap 2,400 chars. Tables are kept intact
when possible; split tables are marked `review_required` in chunk metadata.
This is deterministic character estimation, not model-specific tokenization.
Short sections remain shorter; no invented page/section/year is added.

Default bounds: file ≤20 MiB; text ≤2 million chars; PDF ≤2,000 pages; catalog
≤20,000 rows and 100 columns; ZIP ≤5,000 entries and 50 MB expanded; suspicious
ZIP paths/ratios rejected; at most 100 files/import and 5,000 chunks/document
(256 with embeddings); normalized corpus ≤100 million chars, including history.
Parser process deadline 30 seconds. The service does not unzip arbitrary bundles.
Malformed source jobs fail safely; CLI command failures omit exception traces and
source text. A container/OS memory limit is still needed for hostile native parsers.

## MIT candidates

`manifests/mba_mit.yaml` contains eight official course candidates, checked on
2026-10-25. New Enterprises and Strategic Management download pages were inspected,
as was Marketing Management's lecture/resource page. Actual individual PDF URLs
are recorded for reviewed discovery where confirmed. None is approved by default.
No bulk archive URL is guessed. Course-page text is not imported as lecture notes.

MIT OCW's [terms](https://ocw.mit.edu/pages/privacy-and-terms-of-use/) describe
CC BY-NC-SA 4.0 and exceptions. Curators must review intended use, attribution,
third-party notices and redistribution rights per resource. Public access alone
does not authorize commercialization. Do not imply MIT endorsement.

After curator review, select one exact supported resource URL, record its title,
set its entry's `approved: true`, then explicitly opt into download:

```powershell
.\.venv\Scripts\knowledgectl.exe import-manifest manifests/mba_mit.yaml --download-approved
```

The downloader permits only exact HTTPS `ocw.mit.edu` URLs, public DNS answers,
no redirects/proxies/authentication, and bounded streaming. It never recursively
crawls or extracts ZIPs. If a resource redirects or cannot be verified, use an
authorized manually supplied local file. Raw downloads live in ignored `data/raw`;
normalized text/metadata lives in the knowledge DB. Preserve your manifest and
`sources` export for provenance; never commit a large course corpus.
