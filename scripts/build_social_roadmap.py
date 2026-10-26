"""Map the real roadmap's 43 reading entries to canonical local references."""

import csv
import json
import re
import uuid
from pathlib import Path

import pymupdf

from app.library.catalog import atomic_json, catalog_lock, read_catalog

ROOT = Path("D:/AI/OSCAR/Knowledge")
READINGS = [
    (0, "OpenIntro Statistics", "openintro"),
    (0, "Social Science Research", "social science research"),
    (0, "Doing Economics — CORE Econ", "CORE:doing-economics"),
    (1, "Sapiens", "sapiens"),
    (1, "The Silk Roads", "the silk roads a new history"),
    (1, "Guns, Germs, and Steel", "guns germs and steel"),
    (2, "The Sociological Imagination", "sociological imagination"),
    (2, "OpenStax Psychology 2e", "RANGE:psychology"),
    (2, "Bowling Alone", "bowling alone"),
    (2, "Factfulness", "factfulness"),
    (3, "OpenStax Introduction to Political Science", "RANGE:political"),
    (3, "The Prince and Other Writings", "the prince and other writings"),
    (3, "The Dictator's Handbook", "dictators handbook"),
    (3, "Why Nations Fail", "why nations fail"),
    (3, "A Practical Guide for Policy Analysis", "a practical guide for policy analysis"),
    (3, "The Globalization of World Politics", "globalization of world politics"),
    (4, "CORE Econ: The Economy 2.0 / OpenStax Principles of Economics", "CORE:economy"),
    (4, "Economics: The User's Guide", "economics ha joon"),
    (4, "Freakonomics", "freakonomics"),
    (4, "Development as Freedom", "development as freedom"),
    (4, "Poor Economics", "poor economics"),
    (4, "The Bottom Billion", "bottom billion"),
    (4, "The Wealth of Nations", "GUTENBERG"),
    (4, "Capital in the Twenty-First Century", "capital in the twenty first century"),
    (5, "The Personal MBA", "personal mba"),
    (5, "Financial Intelligence", "financial intelligence"),
    (5, "OpenStax Principles of Accounting, Volume 1", "principles of accounting volume 1"),
    (5, "Playing to Win", "playing to win"),
    (5, "The Lean Startup", "lean startup"),
    (5, "The Goal", "the goal a process"),
    (5, "High Output Management", "high output management"),
    (5, "HBR Manager's Handbook", "managers handbook"),
    (6, "Marketing Management", "marketing management"),
    (6, "This Is Marketing", "this is marketing"),
    (6, "Positioning", "positioning"),
    (6, "How Brands Grow", "how brands grow"),
    (6, "Influence, New and Expanded", "influence new and expanded"),
    (6, "Made to Stick", "made to stick"),
    (6, "Contagious", "contagious"),
    (6, "Traction", "traction"),
    (7, "Justice", "justice michael"),
    (7, "Doughnut Economics", "doughnut economics"),
    (7, "Sustainability: Principles and Practice", "sustainability principles and practice"),
]


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def main():
    output = ROOT / "Catalog"
    approval = json.loads((output / "private-use-approval.json").read_text(encoding="utf-8"))
    with catalog_lock(output):
        value = read_catalog(output / "library.json")
        files = [r for r in value["resources"] if Path(r["root"]) == ROOT]
        compilation = next(r for r in files if "All_119_OPENSTAX" in r["filename"])
        reviewed = json.loads(
            (output / "compilation-reviewed-ranges.json").read_text(encoding="utf-8")
        )
        if reviewed["source_sha256"] != compilation["sha256"]:
            raise ValueError("ROADMAP_PHYSICAL_RANGE_REVIEW_REQUIRED")
        with pymupdf.open(compilation["absolute_path"]) as pdf:
            books = [item for item in pdf.get_toc() if item[0] == 2]
            ranges = []
            for i, (_, title, start) in enumerate(books):
                end = books[i + 1][2] - 1 if i + 1 < len(books) else len(pdf)
                if not start <= end <= len(pdf):
                    continue
                ranges.append(
                    {
                        "title": title,
                        "physical_pdf_start": start,
                        "physical_pdf_end": end,
                        "parent_resource_id": compilation["id"],
                        "edition_verified": False,
                    }
                )
        virtual = []
        for key, title in [
            ("psychology", "OpenStax Psychology 2e"),
            ("political", "OpenStax Introduction to Political Science"),
        ]:
            start, end = reviewed["ranges"][key]["page_range"]
            identifier = str(uuid.uuid5(uuid.UUID(compilation["id"]), f"roadmap:{key}"))
            previous = next(
                (r for r in value.get("virtual_books", []) if r["id"] == identifier), {}
            )
            virtual.append(
                {
                    **compilation,
                    **previous,
                    "id": identifier,
                    "title": title,
                    "parent_resource_id": compilation["id"],
                    "page_range": [start, end],
                    "outline_level": 3,
                    "pdf_pages": end - start + 1,
                    "format": "pdf",
                    "authors": [],
                    "edition": None,
                    "collection": "social-systems",
                    "category": "social-systems",
                    "presence": "PRESENT",
                    "access": {"visibility": "PRIVATE", "owner_id": approval["owner_id"]},
                    "rights": {
                        **compilation["rights"],
                        "permission_status": "APPROVED",
                        "approved_sha256": compilation["sha256"],
                        "evidence": approval["evidence"],
                        "permitted_uses": ["local_index", "private_retrieval"],
                    },
                    "ingestion": previous.get("ingestion", {"status": "CATALOGED"}),
                    "source_range_evidence": "Hash-bound compilation-reviewed-ranges.json physical boundary review; outline-only endpoints are not trusted",
                }
            )
        selected_ids = {r["id"] for r in virtual}
        value["virtual_books"] = [
            r for r in value.get("virtual_books", []) if r["id"] not in selected_ids
        ] + virtual
        atomic_json(output / "library.json", value)
        atomic_json(
            output / "compilation-range-plan.json",
            {
                "parent_resource_id": compilation["id"],
                "physical_pdf_pages": compilation["pdf_pages"],
                "book_level_outline_ranges": ranges,
                "selected_roadmap_resource_ids": [r["id"] for r in virtual],
                "note": "Legacy outline adjacency diagnostic only; not reliable book boundaries. Use compilation-coverage-plan.json for physical coverage and hash-bound reviewed roadmap ranges for attribution.",
                "outline_nodes": len(books),
                "superseded_for_ingestion": True,
            },
        )
        acquired = json.loads((output / "core-acquisition.json").read_text(encoding="utf-8"))
        gutenberg = json.loads((output / "gutenberg-acquisition.json").read_text(encoding="utf-8"))
        mapped = []
        for phase, title, match in READINGS:
            if match.startswith("RANGE:"):
                target = virtual[0] if match.endswith("psychology") else virtual[1]
                identifiers, status = [target["id"]], "PRESENT_IN_COMPILATION_RANGE"
            elif match.startswith("CORE:"):
                book = match[5:]
                paths = {
                    r["path"].casefold()
                    for r in acquired
                    if "path" in r
                    and (
                        r["book"] == book if book != "economy" else r["book"].startswith("economy-")
                    )
                }
                identifiers = [r["id"] for r in files if r["absolute_path"].casefold() in paths]
                status = "OFFICIAL_PUBLIC_HTML_COLLECTED"
            elif match == "GUTENBERG":
                identifiers = [
                    r["id"]
                    for r in files
                    if r["absolute_path"].casefold() == gutenberg["path"].casefold()
                ]
                status = "COMPLETE_PUBLIC_DOMAIN_TEXT_COLLECTED"
            else:
                identifiers = [
                    r["id"]
                    for r in files
                    if r["format"] == "pdf"
                    and all(token in normalize(r["filename"]) for token in normalize(match).split())
                ]
                status = "LOCAL_TITLE_MATCH_EDITION_UNVERIFIED" if identifiers else "MISSING"
            mapped.append(
                {
                    "phase": phase,
                    "reading": title,
                    "availability": status,
                    "resource_ids": identifiers,
                    "indexed": False,
                    "index_note": "Consult live DB/ingestion status; availability is not retrieval readiness.",
                }
            )
        atomic_json(
            output / "social-roadmap-coverage.json",
            {
                "readings": mapped,
                "count": len(mapped),
                "with_local_references": sum(bool(r["resource_ids"]) for r in mapped),
                "scope": "Title/resource coverage, not edition equivalence, completeness of every commercial book or mastery.",
            },
        )
        with (output / "social-roadmap-coverage.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as f:
            writer = csv.DictWriter(
                f, fieldnames=["phase", "reading", "availability", "resource_ids"]
            )
            writer.writeheader()
            writer.writerows(
                {
                    k: "; ".join(v) if isinstance(v, list) else v
                    for k, v in r.items()
                    if k in writer.fieldnames
                }
                for r in mapped
            )
    print(
        "Roadmap readings",
        len(mapped),
        "with local references",
        sum(bool(r["resource_ids"]) for r in mapped),
        "; selected ranges",
        len(virtual),
    )


if __name__ == "__main__":
    main()
