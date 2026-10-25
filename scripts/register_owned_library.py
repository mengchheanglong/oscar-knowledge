"""Apply the recorded owner's private-use approval to the catalog, without moving files."""

import json
import uuid
from pathlib import Path

from app.library.catalog import atomic_json, catalog_lock, read_catalog

ROOT = Path("D:/AI/OSCAR/Knowledge")


def main():
    output = ROOT / "Catalog"
    approval = json.loads((output / "private-use-approval.json").read_text(encoding="utf-8"))
    owner = str(uuid.UUID(approval["owner_id"]))
    acquisitions = json.loads((output / "core-acquisition.json").read_text(encoding="utf-8"))
    acquired = {r["path"].casefold(): r for r in acquisitions if "path" in r}
    gutenberg = json.loads((output / "gutenberg-acquisition.json").read_text(encoding="utf-8"))
    acquired[gutenberg["path"].casefold()] = gutenberg
    review = output / "acquisition-review.json"
    quarantined = (
        {p.casefold() for p in json.loads(review.read_text())["quarantined_paths"]}
        if review.exists()
        else set()
    )
    with catalog_lock(output):
        value = read_catalog(output / "library.json")
        if "approved_pdf_checksums" not in approval:
            approval["approved_pdf_checksums"] = {
                r["id"]: r["rights"]["approved_sha256"]
                for r in value["resources"]
                if Path(r["root"]) == ROOT
                and r["format"] == "pdf"
                and r["rights"].get("evidence") == approval["evidence"]
                and r["rights"].get("approved_sha256")
            }
            atomic_json(output / "private-use-approval.json", approval)
        count = 0
        for row in value["resources"]:
            if Path(row["root"]) != ROOT or row.get("presence") != "PRESENT":
                continue
            if row["absolute_path"].casefold() in quarantined:
                row["rights"].update(permission_status="REVIEW_REQUIRED", permitted_uses=[])
                row["catalog_status"] = "NEEDS_METADATA_REVIEW"
                continue
            acquisition = acquired.get(row["absolute_path"].casefold())
            if row["format"] != "pdf" and not acquisition:
                continue
            if (
                row["format"] == "pdf"
                and approval["approved_pdf_checksums"].get(row["id"]) != row["sha256"]
            ):
                continue
            if acquisition and acquisition["sha256"] != row["sha256"]:
                row["catalog_status"] = "NEEDS_METADATA_REVIEW"
                continue
            row["rights"] = {
                "local_possession": True,
                "permission_status": "APPROVED",
                "permitted_uses": ["local_index", "private_retrieval", "bounded_assistant_context"],
                "approved_sha256": row["sha256"],
                "reviewed_at": approval["approved_at"],
                "evidence": acquisition.get(
                    "scope", "Requested public source for private study; retain original notices"
                )
                if acquisition
                else approval["evidence"],
                "sharing_authorized": False,
                "commercial_redistribution_authorized": False,
            }
            row["access"] = {"visibility": "PRIVATE", "owner_id": owner}
            row["catalog_status"] = "APPROVED"
            row["ocr_tessdata"] = "D:/AI/OSCAR/tools/tessdata"
            if acquisition:
                row["source_url"] = acquisition["url"]
                row["title"] = acquisition["title"][:500]
                row["authors"] = [acquisition["author"]] if acquisition.get("author") else []
                row["metadata_status"] = "VERIFIED"
                row["metadata_evidence"] = (
                    "Hash-verified acquisition manifest and original public HTML title; edition/year remain unknown"
                )
            count += 1
        atomic_json(output / "library.json", value)
    print("Private-use approvals registered:", count, "; no shared grants or ingestion performed")


if __name__ == "__main__":
    main()
