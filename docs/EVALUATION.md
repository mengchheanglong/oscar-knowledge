# Evaluation

`fixtures/eval_questions.json` is versioned and contains 20 manually constructed
question-to-source expectations across entrepreneurship, strategy, marketing,
economics, finance and decision science. Gold canonical source keys resolve to
the actual document UUIDs after `import-manifest fixtures/demo.yaml`.

```powershell
.\.venv\Scripts\knowledgectl.exe import-manifest fixtures/demo.yaml
.\.venv\Scripts\knowledgectl.exe eval fixtures/eval_questions.json
```

The CLI reports document-level Hit@6, Recall@6 and MRR@6. It refuses evaluation
when gold sources have not been imported. Recall counts unique returned gold
documents; reciprocal rank uses the first matching chunk's result rank. This
dataset validates routing, keyword ranking and provenance on original synthetic
notes. It is intentionally easy and is **not evidence of real MBA-corpus quality**.
Scores from an actual run are recorded in IMPLEMENTATION_REPORT.md.

Real corpus evaluation requires curator-approved documents and a separate gold
set with physical PDF pages and expected passages. Compare keyword/exact vector/
hybrid results, latency, diversity, support for each cited claim and false positives
on unanswerable questions. Pay particular attention to slide extraction and tables.
No live-model, real-source retrieval, reranker, or million-chunk performance result
has been measured by fixture-only tests. Add real-source evaluation before demoing
university-source claims or making retrieval-quality/scaling promises.

Deferred: OCR, Whisper, custom training, knowledge graphs, agentic crawlers,
distributed indexing/sharding, vector DB replacement, mandatory reranking,
private tenancy, paid/DRM media, and replacing OSCAR's existing RAG pipeline.
