"""Read-only verification by default; --apply binds only verified legacy preparation metadata."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.models import LibraryBook
from app.db.session import session
from app.library.catalog import atomic_json, read_catalog
from app.library.legacy import adopt_legacy_preparation

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    catalog = read_catalog(ROOT / "library.json")
    rows = {r["id"]: r for r in catalog["resources"] + catalog.get("virtual_books", [])}
    status = json.loads((ROOT / "ingestion-status.json").read_text(encoding="utf-8"))
    results = []
    with session() as db:
        identifiers = [
            str(b.id)
            for b in db.scalars(
                select(LibraryBook).where(
                    LibraryBook.active_generation > 0,
                    LibraryBook.preparation_sha256.is_(None),
                    LibraryBook.approved.is_(True),
                )
            )
        ]
        for identifier in identifiers:
            snapshot = status["resources"][identifier]
            state = json.loads(Path(snapshot["preparation_path"]).read_text(encoding="utf-8"))
            results.append(
                adopt_legacy_preparation(
                    db, rows[identifier], state, get_settings(), apply=args.apply
                )
            )
    atomic_json(ROOT / "reports" / "legacy-preparation-adoption.json", {"results": results})
    print(
        "Verified legacy references",
        len(results),
        "metadata applied",
        args.apply,
        "source/chunk/vector writes",
        0,
    )


if __name__ == "__main__":
    main()
