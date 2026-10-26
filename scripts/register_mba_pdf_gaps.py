"""Reuse audited MBA text and privately prepare only absent PDFs/page supplements.

The existing shared documents, grants and quarantines are never changed. The
owner's recorded PDF authorization is bound to the exact original checksums.
"""

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.models import Document
from app.db.session import session
from app.library.catalog import atomic_json, catalog_lock, digest, read_catalog
from app.library.source import verify_source

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def require_owner_grant(approval, row):
    if approval.get("approved_mba_pdf_checksums", {}).get(row["id"]) != row["sha256"]:
        raise ValueError("MBA_HASH_BOUND_OWNER_APPROVAL_REQUIRED")


def contiguous_ranges(pages):
    result = []
    for page in sorted(set(pages)):
        if result and result[-1][1] + 1 == page:
            result[-1][1] = page
        else:
            result.append([page, page])
    return result


def register(output):
    audit_path = output / "reports/mba-pdf-coverage-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    approval = json.loads((output / "private-use-approval.json").read_text(encoding="utf-8"))
    owner = str(uuid.UUID(approval["owner_id"]))
    manifest = json.loads(
        Path("D:/AI/OSCAR/mba-corpus/2026-10-25/shared-import/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    shared = {r["canonical_key"]: r for r in manifest}
    with session() as db:
        documents = {str(d.id): d for d in db.scalars(select(Document))}
    with catalog_lock(output):
        catalog = read_catalog(output / "library.json")
        originals = {r["id"]: r for r in catalog["resources"]}
        prior = {r["id"]: r for r in catalog.get("virtual_books", [])}
        children = []
        plan = []
        for evidence in audit["resources"]:
            row = originals[evidence["id"]]
            require_owner_grant(approval, row)
            if row["sha256"] != evidence["sha256"] or row["pdf_pages"] != evidence["pdf_pages"]:
                raise ValueError("MBA_AUDIT_SOURCE_CHANGED")
            if Path(row["root"]) != Path("D:/AI/OSCAR/mba-corpus") or row["format"] != "pdf":
                raise ValueError("MBA_AUDIT_SOURCE_SCOPE")
            verify_source(row, force=True)
            linked = []
            document_proofs = {}
            for identifier in evidence["existing_document_ids"]:
                document = documents[identifier]
                prepared = shared.get(document.canonical_key)
                if (
                    not prepared
                    or not document.approved
                    or document.active_revision < 1
                    or not document.embedding_identity
                    or prepared["source_url"] != evidence["source_url"]
                    or document.content_sha256 != prepared["sha256"]
                    or digest(Path(prepared["path"])) != prepared["sha256"]
                ):
                    raise ValueError("MBA_EXISTING_TEXT_CHANGED_REAUDIT_REQUIRED")
                linked.append(identifier)
                document_proofs[identifier] = {
                    "content_sha256": document.content_sha256,
                    "active_revision": document.active_revision,
                    "embedding_identity": document.embedding_identity,
                }
            previous_rights = row["rights"]
            if previous_rights.get("permission_status") == "REVOKED":
                raise ValueError("MBA_PRIVATE_GRANT_REVOKED")
            row["rights"] = {
                "local_possession": True,
                "permission_status": "APPROVED",
                "permitted_uses": ["local_index", "private_retrieval", "bounded_assistant_context"],
                "approved_sha256": row["sha256"],
                "reviewed_at": approval["approved_at"],
                "evidence": approval["evidence"],
                "sharing_authorized": False,
                "commercial_redistribution_authorized": False,
            }
            row.update(
                access={"visibility": "PRIVATE", "owner_id": owner},
                collection="personal-library",
                catalog_status="APPROVED",
                ocr_tessdata="D:/AI/OSCAR/tools/tessdata",
                source_url=evidence["source_url"],
                source_notice="Private original PDF. Retain source notices; verify formulas, diagrams and extracted layout against the physical PDF page.",
            )
            ranges = contiguous_ranges(
                evidence["missing_or_altered_text_pages"] + evidence["low_text_pages"]
            )
            if not linked:
                row["preparation_version"] = 3
                kind = "PRIVATE_FULL_PDF"
            else:
                row["mba_text_reuse"] = {
                    "audit_sha256": digest(audit_path),
                    "source_sha256": row["sha256"],
                    "document_ids": linked,
                    "document_proofs": document_proofs,
                    "supplement_ranges": ranges,
                    "graphic_interpretation": "Text coverage proof does not certify every visual label or formula.",
                }
                row["ingestion"] = {
                    "status": "EXISTING_MBA_TEXT_PENDING_SUPPLEMENTS"
                    if ranges
                    else "INDEXED_TEXT_VIA_EXISTING_MBA",
                    "source_sha256": row["sha256"],
                    "source_matches_catalog": True,
                    "existing_document_ids": linked,
                    "retrievable": not ranges,
                    "supplement_ranges": ranges,
                }
                kind = "EXISTING_MBA_TEXT_WITH_SUPPLEMENTS" if ranges else "EXISTING_MBA_TEXT"
                for first, last in ranges:
                    identifier = str(
                        uuid.uuid5(uuid.UUID(row["id"]), f"mba-page-supplement-v1:{first}:{last}")
                    )
                    child = {
                        **row,
                        "id": identifier,
                        "parent_resource_id": row["id"],
                        "mba_page_supplement": True,
                        "page_range": [first, last],
                        "pdf_pages": last - first + 1,
                        "preparation_version": 3,
                        "title": f"{row['title'][:420]} — original PDF pages {first}–{last}",
                        "outline_level": 0,
                        "ingestion": prior.get(identifier, {}).get(
                            "ingestion", {"status": "CATALOGED"}
                        ),
                    }
                    child.pop("mba_text_reuse", None)
                    previous = prior.get(identifier, {})
                    if previous.get("sha256") == row["sha256"]:
                        for field in [
                            "rights",
                            "access",
                            "page_reviews",
                            "preparation_revision",
                            "physical_page_buckets",
                        ]:
                            if field in previous:
                                child[field] = previous[field]
                    children.append(child)
            plan.append({"id": row["id"], "kind": kind, "supplement_ranges": ranges})
        catalog["virtual_books"] = [
            r for r in catalog.get("virtual_books", []) if not r.get("mba_page_supplement")
        ] + children
        atomic_json(output / "library.json", catalog)
        receipt = {
            "created_at": datetime.now(UTC).isoformat(),
            "audit_sha256": digest(audit_path),
            "original_pdfs": len(plan),
            "private_full_pdfs": sum(r["kind"] == "PRIVATE_FULL_PDF" for r in plan),
            "existing_text_pdfs": sum(r["kind"] != "PRIVATE_FULL_PDF" for r in plan),
            "supplement_references": len(children),
            "supplement_pages": sum(r["pdf_pages"] for r in children),
            "resources": plan,
            "shared_documents_or_permissions_changed": False,
        }
        atomic_json(output / "mba-pdf-completion-plan.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != "resources"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true", required=True)
    arguments = parser.parse_args()
    register(arguments.output)
