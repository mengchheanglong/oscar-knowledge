# Initial readiness audit — 2026-10-25

All three checkouts were clean and synchronized with `origin/main` at audit time:
Knowledge `be54e22`, backend `82bbe93`, frontend `0dac175`. Compared with remote
`develop`, each local HEAD was one commit ahead, with no missing remote commits.
No resets, rebases, force-pushes or develop-to-main merges were performed.
Backend/frontend AGENTS.md explicitly require main. Knowledge has no AGENTS.md;
this brief requests develop there, so its develop was fast-forwarded to the Qwen
main baseline before this task's edits. Existing commits and main are preserved.

| Category | Actual audit finding |
| --- | --- |
| Complete | Local Ollama, Qwen 1024 provider, additive migration 0002, source-preserving re-embedding, real prior synthetic integration, backend client and frontend Course Knowledge opt-in |
| Reverified now | Ollama native single/batch output, dimensions/order/nonzero/finite values, GPU execution, Knowledge DB/schema/runtime doctor; seven compatible active vectors |
| Implemented but requiring current regression | Backend auth/scope/context/citation pipeline; all-repository current test suites; outage handling and startup sequence |
| Missing | Approved real educational corpus, real passage gold labels and Hit/Recall/MRR@5 evaluation, real-source OSCAR demo, aggregate operational health report |
| Broken or stale documentation | Brief's claim that Qwen is unpublished is stale; README branch references still say develop despite newer workflow instructions |
| Approval | Three specified MIT OCW PDFs explicitly approved by the user in this chat for the noncommercial local demonstration; other university resources remain unapproved |
| Deferred | Production hosting/security review, large corpus, OCR/diagram understanding, transcription, ANN/reranking/GraphRAG, broader rights review |

Running components: Windows Ollama on loopback 11434 (RTX 3050 GPU); Knowledge
API Docker on loopback 8010; independent Knowledge PostgreSQL 43114, disposable
test DB 43115; native OSCAR backend 43101, frontend 43100; OSCAR DB 43104 and test
43105. Unrelated `ofd-research-postgres` was observed and left untouched.
Secrets stay in ignored local configuration. The model weights and executables
remain on D:. Backend generation configuration and MAVIS embeddings are preserved.

Accepted-decision lookup through OSCAR MCP for AIW succeeded and returned no
accepted ADRs. No task status was invented or changed. Before corpus ingestion,
the Knowledge database was backed up to
`D:\AI\Ollama\backups\knowledge-before-mba.dump`.
