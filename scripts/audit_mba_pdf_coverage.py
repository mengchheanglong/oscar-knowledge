"""Prove original MBA embedded text is present in approved prepared documents.

This is a read-only filesystem/database audit apart from its derived JSON report.
Source URLs are locators; reuse requires exact source/prepared checksums and the
current approved database revision. Low-text pages are separately supplemented.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf
from sqlalchemy import select

from app.db.models import Document
from app.db.session import session
from app.library.catalog import atomic_json, digest, read_catalog
from app.library.source import verify_source

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")
CORPUS = Path("D:/AI/OSCAR/mba-corpus/2026-10-25")


def normalized(text):
    return " ".join(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text).split())


def main():
    catalog = read_catalog(ROOT / "library.json")
    downloads = {}
    for path in sorted(CORPUS.glob("*/manifest.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        for entry in data.get("files", []):
            if entry.get("sha256") and entry.get("url"):
                downloads.setdefault(entry["sha256"], {**entry, "source_id": path.parent.name})
    manifest = json.loads((CORPUS / "shared-import/manifest.json").read_text(encoding="utf-8"))
    with session() as db:
        documents = {d.canonical_key: d for d in db.scalars(select(Document))}
    prepared = defaultdict(list)
    for entry in manifest:
        document = documents.get(entry["canonical_key"])
        path = Path(entry["path"])
        if (
            not document
            or not document.approved
            or document.active_revision < 1
            or not document.embedding_identity
            or document.content_sha256 != entry["sha256"]
            or not path.exists()
            or digest(path) != entry["sha256"]
        ):
            continue
        prepared[entry["source_url"]].append((document, path.read_text(encoding="utf-8")))
    results = []
    for row in catalog["resources"]:
        if Path(row["root"]) != CORPUS.parent or row["format"] != "pdf":
            continue
        verify_source(row, force=True)
        download = downloads.get(row["sha256"], {})
        url = download.get("url")
        linked = prepared.get(url, [])
        fragments = defaultdict(list)
        for document, content in linked:
            sections = re.split(r"(?m)^## Original PDF page (\d+)\s*$", content)
            for index in range(1, len(sections), 2):
                fragments[int(sections[index])].append(normalized(sections[index + 1]))
        missing, low = [], []
        with pymupdf.open(row["absolute_path"]) as pdf:
            if len(pdf) != row["pdf_pages"]:
                raise ValueError("MBA_PDF_PAGE_COUNT_CHANGED")
            for number, page in enumerate(pdf, 1):
                text = normalized(page.get_text())
                if sum(c.isalnum() for c in text) < 20:
                    low.append(number)
                if text and text not in " ".join(fragments[number]):
                    missing.append(number)
        valid = bool(download and linked and not missing)
        results.append(
            {
                "id": row["id"],
                "sha256": row["sha256"],
                "pdf_pages": row["pdf_pages"],
                "status": "EXISTING_SHARED_TEXT" if valid else "PRIVATE_INDEX_REQUIRED",
                "source_url": url,
                "source_id": download.get("source_id"),
                "download_sha_matches": bool(download),
                "existing_document_ids": [str(d.id) for d, _ in linked],
                "prepared_pages": len([p for p, values in fragments.items() if values]),
                "missing_or_altered_text_pages": missing,
                "low_text_pages": low,
            }
        )
        if len(results) % 50 == 0:
            print("Original MBA PDFs audited", len(results), flush=True)
    report = {
        "resources": results,
        "summary": dict(Counter(r["status"] for r in results)),
        "scope": "Shared text reuse requires matched download provenance and complete original embedded-text coverage; graphic interpretation remains a separate limitation.",
    }
    atomic_json(ROOT / "reports/mba-pdf-coverage-audit.json", report)
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
