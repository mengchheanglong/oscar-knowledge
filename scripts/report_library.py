"""Generate local reports; optionally verify a pre-library ID/hash baseline."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.db.session import session
from app.library.catalog import atomic_json, read_catalog
from app.library.status import sync_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", type=Path, default=Path("D:/AI/OSCAR/Knowledge/Catalog"))
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    root = args.catalog_dir
    reports = root / "reports"
    with session() as db:
        summary = sync_status(db, root, verify_originals=True)
        if args.baseline:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            checks = {}
            statements = {
                "documents": "SELECT id::text, active_revision::text, content_sha256 FROM documents",
                "chunks": "SELECT id::text, document_id::text, revision::text, md5(text) FROM chunks",
                "vectors": "SELECT chunk_id::text, identity, md5(coalesce(embedding_1024::text,embedding_1536::text)) FROM chunk_embeddings",
            }
            for name, sql in statements.items():
                identifier = "chunk_id" if name == "vectors" else "id"
                actual = set()
                identifiers = list({r[0] for r in baseline[name]})
                for start in range(0, len(identifiers), 1000):
                    bounded = sql + f" WHERE {identifier} = ANY(CAST(:ids AS uuid[]))"
                    actual.update(
                        tuple(r)
                        for r in db.execute(
                            text(bounded), {"ids": identifiers[start : start + 1000]}
                        )
                    )
                checks[name] = {
                    "baseline_rows": len(baseline[name]),
                    "missing_or_changed": sum(tuple(r) not in actual for r in baseline[name]),
                }
            atomic_json(
                reports / "preservation-audit.json",
                {"checked_at": datetime.now(UTC).isoformat(), "checks": checks},
            )
            if any(r["missing_or_changed"] for r in checks.values()):
                raise ValueError("BASELINE_PRESERVATION_FAILED")
    catalog = read_catalog(root / "library.json")
    status = json.loads((root / "ingestion-status.json").read_text(encoding="utf-8"))
    resources = catalog["resources"] + catalog.get("virtual_books", [])
    pending = [
        r
        for r in resources
        if r.get("rights", {}).get("permission_status") == "APPROVED"
        and r.get("access", {}).get("visibility") == "PRIVATE"
        and r.get("ingestion", {}).get("status")
        not in {
            "INDEXED",
            "INDEXED_VIA_RANGES",
            "INDEXED_TEXT_VIA_EXISTING_MBA",
            "REVIEWED_NON_TEXT",
        }
    ]
    coverage = json.loads((root / "social-roadmap-coverage.json").read_text(encoding="utf-8"))
    audit = json.loads((reports / "extraction-audit.json").read_text(encoding="utf-8"))
    originals = json.loads((reports / "original-file-audit.json").read_text(encoding="utf-8"))
    duplicates = json.loads((root / "duplicates.json").read_text(encoding="utf-8"))
    ready_pdf = [
        r
        for r in resources
        if r["format"] == "pdf" and status["resources"].get(r["id"], {}).get("retrievable")
    ]
    lines = [
        "# Local library ingestion report",
        "",
        f"Generated {datetime.now(UTC).isoformat()}. Derived snapshots, not a second metadata authority.",
        "",
        f"{summary['retrievable_references']} private references: {len(ready_pdf)} PDF references and {summary['retrievable_references'] - len(ready_pdf)} public HTML sections. {summary['active_parts']} active document parts; {summary['active_chunks']} chunks and {summary['active_vectors']} current-model vector rows.",
        "",
        f"Collections: {summary['collections']}. Status: {summary['states']}.",
        "",
        f"MBA original PDFs reusing approved existing text: {summary.get('mba_original_pdfs_reusing_existing_text', 0)}; complete with all required page supplements: {summary.get('mba_original_pdfs_complete_with_supplements', 0)}. These reuse counts are separate from new private book/vector counts; no existing shared document or grant was changed.",
        "",
        f"Prepared PDF coverage spans {summary['pdf_pages_in_prepared_references']:,} physical pages, including blanks and excluded unreadable pages. Local OCR produced text for {summary['ocr_pages']} pages; {summary['unresolved_pages']} pages remain unresolved across {summary['states'].get('PARTIALLY_INDEXED', 0)} explicitly partial references. Reviewed visual descriptions/transcriptions are distinct from embedded text; descriptions do not reproduce every graphical detail.",
        "",
        f"Roadmap: {coverage['with_local_references']}/{coverage['count']} readings have local matches; {coverage['indexed_readings']} have retrievable references. See social-roadmap-coverage.csv for per-reading partial coverage. Title matches are not verified edition equivalence.",
        "",
        f"Original PDF audit: {len(originals['results'])} files; all bytes, size and modification time unchanged: {originals['all_unchanged']}. Embedded-text audit: {sum(r.get('checked_embedded_pages', 0) for r in audit['results']):,} pages; repair gates {sum(r['status'] != 'PASS' for r in audit['results'])}. OCR formulas require visual review.",
        "",
        f"Duplicates: {len(duplicates['exact'])} SHA groups across both roots. Nothing deleted or merged; duplicate copies do not transfer rights.",
        "",
        "Compilation coverage (live active ranges): "
        + json.dumps(status.get("compilations", {}), sort_keys=True),
        "",
        "The earlier 211 outline-node / 209 remaining-book estimate was incorrect: nested binders, repeated books and unrelated inserted material invalidate those book boundaries. The superseding compilation-coverage-plan.json registers disjoint physical windows over all 156,324 pages. The corrected Political Science range is 10421–11059; the Psychology range is 35189–35971. The other windows are labeled mixed compilation, not verified OpenStax editions. Original content is retained without attributing unrelated text to OpenStax. No permission question remains for these owned source bytes.",
        "",
        "Other limits: commercial-book editions/full-publication completeness are unverified; some local files are summaries. Public HTML collection retains source URLs/notices but does not mirror interactive/media assets or gated solutions. Two ambiguous prior HTML acquisitions are retained and quarantined. Original MBA content remains separate and shared only under its existing approvals.",
        "",
        "Approved private resources still requiring processing or page review:",
        "",
    ]
    lines += [f"- {r['id']}: {r['title']} ({r.get('pdf_pages')} pages)" for r in pending]
    (reports / "INGESTION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    evaluation = json.loads((reports / "retrieval-evaluation.json").read_text(encoding="utf-8"))
    table = [
        "# Retrieval evaluation",
        "",
        "Six explicit gold books across strategy, finance, quantitative reasoning, product, leadership and communication; one gold book per question. Recall@5 here means gold-book recall, not chunk-level recall. Eighteen real requests; no answer generation in this benchmark.",
        "",
        "| Mode | Hit@5 | Recall@5 | MRR@5 | Median seconds |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, r in evaluation["summary"].items():
        table.append(
            f"| {mode} | {r['hit_at_5']:.3f} | {r['recall_at_5']:.3f} | {r['mrr_at_5']:.3f} | {r['median_seconds']:.4f} |"
        )
    probe = evaluation["embedding_probe"]
    table += [
        "",
        f"Local probe: {probe['passages']} passages, {probe['dimensions']} dimensions, {probe['seconds']} seconds, {probe['passages_per_second']} passages/sec including model verification and HTTP overhead. No vector dump.",
        "",
        "Four unique scripted configured-model chat requests verified Finance, Social Systems, unanswerable abstention and opt-out; saved citations/replay/scope-change conflict passed. One additional browser chat cited Thinking in Systems and its physical PDF page. These demonstrate integration and attribution, not universal semantic claim support or answer accuracy. Private receipts remain outside Git.",
        "",
        "Original initial benchmark retained separately. Current source question results and scope checks: retrieval-evaluation.json. The six-question sample does not certify library-wide recall or MBA equivalence.",
    ]
    (reports / "RETRIEVAL_EVALUATION.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    security = [
        "# Private-library security review",
        "",
        "Local deployment only. Backend validates the ordinary authenticated OSCAR user; only trusted backend code signs a short-lived subject/audience/body-hash assertion with a separate secret. Service bearer alone cannot read private books or private counts. No client-supplied owner ID grants access.",
        "",
        "Owner, collection visibility, approval, active book generation and active document revision are filtered before retrieval. Returned evidence is rechecked against current approval/revision. Public collection listing excludes private slugs. Only owner-scoped ready-reference counts are exposed, without filenames or titles. Private embedding uses local Ollama; no source PDFs are served/downloaded by the API.",
        "",
        "Live checks: " + json.dumps(evaluation["security"], sort_keys=True),
        "",
        "Isolated tests cover revoked grants (including revoke-before-registration race), unapproved sources, changed-file staging, absent chunks, signed-scope forgery/expiry/body mismatch, owner isolation, shared scope isolation and no local paths. Backend validates unknown citations and conversations through existing guards. Retrieved text cannot authorize actions or become MAVIS memory automatically.",
        "",
        "Boundary: trusted local operator, backend signing key, filesystem/DB administrator and existing LLM provider remain trusted. Bounded retrieved snippets are sent to the configured chat model only when Reference knowledge is opted in. This does not protect against a compromised machine/admin or claim a public-production security audit. Retain source notices and private grants; no commercial/shared grant follows from ownership.",
        "",
        "Disable private access by removing the matching private-scope keys from both service configurations and restarting. Preserve additive schema/data and shared MBA settings. Explicit library revoke immediately denies reads while retaining original PDFs and historical vectors.",
    ]
    (reports / "SECURITY_REVIEW.md").write_text("\n".join(security) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": summary,
                "roadmap_indexed_readings": coverage["indexed_readings"],
                "pending_approved_private": len(pending),
                "originals_unchanged": originals["all_unchanged"],
            }
        )
    )


if __name__ == "__main__":
    main()
