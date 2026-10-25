"""Download only the three user-authorized PDFs for local review; never approve/import."""

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf
import yaml

from app.config import get_settings
from app.ingestion.manifest import download


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", required=True)
    parser.parse_args()
    entries = yaml.safe_load(Path("manifests/mba_mit.yaml").read_text())["entries"][:3]
    review = []
    for entry in entries:
        path = Path("data/raw/mba") / entry["subject"].lower() / Path(entry["download_url"]).name
        if not path.exists():
            download(entry["download_url"], path, get_settings())
        with pymupdf.open(path) as pdf:
            pages = [p.get_text() for p in pdf]
            output = Path("data/processed/mba") / entry["course_code"]
            output.mkdir(parents=True, exist_ok=True)
            for number, text in enumerate(pages, 1):
                (output / f"page-{number:03}.txt").write_text(text, encoding="utf-8")
            review.append(
                {
                    "course": entry["course_code"],
                    "source_url": entry["download_url"],
                    "path": str(path),
                    "pages": len(pdf),
                    "page_characters": [len(t.strip()) for t in pages],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "approval_scope": "User approved noncommercial local demo; not an import receipt",
                }
            )
    target = Path("data/evaluations/mba_extraction_review.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(review, indent=2), encoding="utf-8")
    print(json.dumps(review, indent=2))


if __name__ == "__main__":
    main()
