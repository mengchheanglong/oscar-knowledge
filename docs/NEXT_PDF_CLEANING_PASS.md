# Deferred: complete page-content cleaning

Deferred at the user's request on 2026-10-26. Stop cleaning work after saving
this handoff and pushing the completed changes to `main`. Resume only when the
user asks. No background or scheduled continuation was requested.

## Actual remaining scope

All 672 original PDFs (198,758 pages) have recorded processing outcomes. This
does not mean every page's full content has been accurately transcribed or
fact-checked. Keep processing coverage, extraction fidelity, source correctness
and educational coverage as distinct claims.

The latest source-bound inventory identifies 1,742 distinct OCR source/page
pairs: 427 quantitative/table candidates, 1,294 other OCR pages and 21 recorded
blank outcomes. Signals are automatic priorities, not confirmed defect counts.
The 427 include 133 remaining pages in the quantitative finance interview book.
Separately, 68 previously repaired pages currently use selected reviewed
excerpts/descriptions and need full-content treatment where meaningful material
was omitted. Do not double-count those 68 as remaining OCR pages.

A purposive six-page diagnostic across four source PDFs confirmed equation/sign
loss, lost chart/tree relationships and an original-source mathematical erratum.
It is not a representative defect-rate sample or a full-cleaning throughput
benchmark. The earlier 2–4 week estimate was preliminary; 3,313 hours was only
the arithmetic for one minute on every original page, not remaining work.

## Recommended next batch

1. Fully clean 25 quantitative pages, starting with the confirmed diagnostic
   defects and quantitative finance material. Preserve all meaningful visible
   prose, formulas, tables, footnotes, legends and question continuations.
2. Compare with rendered originals, check numerical examples and mathematical
   conditions, and distinguish source errata from OCR errors. Retain the
   attributed original statement alongside an explicit correction where needed.
3. Preserve meaningful diagram structure and the original image. Do not invent
   exact values from plotted lines, hidden/cropped nodes or omitted illustrations.
4. Activate verified batches through new private preparation revisions. Preserve
   original PDFs, old preparations, IDs/revisions where supported, shared
   baseline rows, ownership, licenses and model identity. Use accurate extraction
   labels; do not describe selected excerpts as full transcriptions.
5. Check source hashes, active-generation completeness, physical-page citations,
   vector coverage and other-owner denial. Measure the full 25-page process
   through activation before estimating the remaining workload by page type.
6. Continue through the quantitative candidates and excerpt-based pages, then
   the other OCR pages. Also assess meaningful existing visual-description pages;
   the OCR queue is not an inventory of every image-bearing page in every PDF.

Completion means all available meaningful content represented with explicit
limitations. It cannot recover illustrations absent from the supplied source or
guarantee factual truth in every publication. Do not repeat all-library audits
unless new changes justify them; use focused batch checks first.

## Private evidence and directories

- Originals: `D:\AI\OSCAR\Knowledge` category folders, `MBA`, `Social Systems`.
- MBA corpus, study units and capstones: `D:\AI\OSCAR\mba-corpus\2026-10-25`.
- Preparations: `D:\AI\OSCAR\Knowledge\Catalog\ingestion-cache`; use
  `ingestion-status.json` for active paths, since historical revisions remain.
- Completed review receipts:
  `D:\AI\OSCAR\Knowledge\Catalog\reports\quality-review\2026-10-26\corrected\source-review`.
- Next-pass inventory and six rendered samples: the `next-cleaning-pass`
  subdirectory there. Read `NEXT_CLEANING_PLAN.md`, `OCR_PAGE_INVENTORY.json`,
  `TIMED_PILOT_PACKET.json` and `PILOT_REVIEW_RESULTS.json` before resuming.

This diagnostic pass changed no indexed content. The previous completed repair
round is documented in [source review completion](SOURCE_REVIEW_COMPLETION_2026_10_26.md).
Keep private content, source images, decision packets, credentials and model
weights outside Git. Continue development directly on `main`.
