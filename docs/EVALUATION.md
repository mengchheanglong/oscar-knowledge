# Evaluation

Real MIT passage labels and Hit/Recall/MRR@5 results are now available in
[the readiness report](KNOWLEDGE_HACKATHON_READINESS.md#d-retrieval-evaluation).
Use `knowledgectl eval-passages manifests/mba_retrieval_gold.json --mode hybrid`.
It verifies the approved source hash, active revision, page and anchor before
scoring, records actual fallback/locator behavior and evaluates unanswerable
questions separately. Nongold candidates are unjudged; no universal precision
or abstention guarantee follows from these labels.

`fixtures/eval_questions.json` is versioned and contains 20 manually constructed
question-to-source expectations across entrepreneurship, strategy, marketing,
economics, finance and decision science. Gold canonical source keys resolve to
the actual document UUIDs after `import-manifest fixtures/demo.yaml`.

```powershell
.\.venv\Scripts\knowledgectl.exe import-manifest fixtures/demo.yaml
.\.venv\Scripts\knowledgectl.exe eval fixtures/eval_questions.json
.\.venv\Scripts\knowledgectl.exe eval fixtures/eval_questions.json --mode semantic
.\.venv\Scripts\knowledgectl.exe eval fixtures/eval_questions.json --mode hybrid
```

The CLI reports document-level Hit@6, Recall@6 and MRR@6. It refuses evaluation
when gold sources have not been imported. Recall counts unique returned gold
documents; reciprocal rank uses the first matching chunk's result rank. This
dataset validates routing, keyword ranking and provenance on original synthetic
notes. It is intentionally easy and is **not evidence of real MBA-corpus quality**.
Scores from an actual run are recorded in IMPLEMENTATION_REPORT.md.
Local Qwen with/without query instructions and measured latencies are recorded in
[QWEN_SERVICE_VERIFICATION.json](QWEN_SERVICE_VERIFICATION.json). This comparison
uses real embeddings on the same small synthetic dataset and establishes no
university-corpus or general quality improvement.

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
