"""Local-only metadata. This module never submits documents for retrieval."""

import hashlib
import json
import os
import re
import uuid
from typing import Any
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.ingestion.loaders import SUPPORTED

FORMATS = SUPPORTED | {".epub"}
CATEGORIES = {
    "01-Strategy-and-Decision": "strategy-and-decision",
    "02-Product-and-Growth": "product-and-growth",
    "03-Society-and-Power": "society-and-power",
    "04-Leadership-and-Execution": "leadership-and-execution",
    "05-AI-and-Engineering": "ai-and-engineering",
    "06-Finance-and-Quantitative": "finance-and-quantitative",
    "07-Communication-and-Writing": "communication-and-writing",
    "MBA": "mba",
    "Social Systems": "social-systems",
}
NAMESPACE = uuid.UUID("501c9999-7afb-4b85-a7bf-d930dbbd2865")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def catalog_lock(output: Path):
    lock = output / ".catalog.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def read_catalog(path: Path):
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1:
            raise ValueError("CATALOG_VERSION_UNSUPPORTED")
        return value
    return {"schema_version": 1, "resources": []}


def clean_title(name: str):
    name = re.sub(r"_?OceanofPDF\.com_?", "", name, flags=re.I).replace("_", " ")
    return re.sub(r"\s+", " ", name).strip(" .-")[:500] or "Untitled"


def usable_metadata(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    if (
        not value
        or len(value) > 500
        or re.search(r"microsoft|untitled|acrobat|print to pdf|[\\/]|\.docx?$", value, re.I)
    ):
        return None
    return value


def inspect_pdf(path: Path):
    """At most three pages, clipped text areas; no full-document extraction."""
    import pymupdf

    result: dict[str, Any] = {"pdf_pages": None, "embedded_title": None, "embedded_author": None}
    try:
        with pymupdf.open(path) as pdf:
            result["pdf_pages"] = len(pdf)
            if len(pdf) > 5000:
                return {**result, "extraction": "OVERSIZED_REVIEW_REQUIRED"}
            if pdf.needs_pass or not len(pdf):
                return {**result, "extraction": "ENCRYPTED_OR_UNREADABLE"}
            meta = pdf.metadata or {}
            result.update(
                embedded_title=usable_metadata(meta.get("title")),
                embedded_author=usable_metadata(meta.get("author")),
            )
            pages = sorted({0, len(pdf) // 2, len(pdf) - 1})
            lengths = []
            for number in pages:
                page = pdf[number]
                sample = page.get_text(clip=page.rect)[:12000]
                lengths.append(sum(c.isalnum() for c in sample))
            result["sampled_pdf_pages"] = [p + 1 for p in pages]
            result["sampled_alphanumeric_chars"] = lengths
            good = sum(n >= 40 for n in lengths)
            result["extraction"] = (
                "TEXT_EXTRACTABLE"
                if good == len(lengths)
                else "PARTIALLY_EXTRACTABLE"
                if good
                else "OCR_REQUIRED"
            )
    except Exception:
        result["extraction"] = "ENCRYPTED_OR_UNREADABLE"
    return result


def scan(roots: list[Path], previous: dict, *, verify=False, max_files=100000, progress=None):
    old = previous.get("resources", [])
    old_paths = {r["absolute_path"].casefold(): r for r in old}
    old_hashes = defaultdict(list)
    for r in old:
        if r.get("sha256"):
            old_hashes[(r["root"], r["sha256"])].append(r)
    seen, used_ids, records, errors = set(), set(), [], []
    events: Counter[str] = Counter()
    all_paths = []
    root_states = {}
    for root in roots:
        root = root.absolute()
        root_states[str(root)] = root.is_dir() and not root.is_symlink()
        if not root_states[str(root)]:
            errors.append({"path": str(root), "code": "ROOT_UNAVAILABLE"})
            continue

        def onerror(error):
            errors.append({"path": str(error.filename), "code": "DIRECTORY_UNAVAILABLE"})

        for base, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
            dirs[:] = sorted(
                d
                for d in dirs
                if d.casefold()
                not in {"catalog", ".git", "__pycache__", "private-backups", "node_modules"}
                and not Path(base, d).is_symlink()
                and not Path(base, d).is_junction()
            )
            for name in sorted(files):
                p = Path(base, name)
                if p.suffix.lower() not in FORMATS or name.startswith(("~$", ".")):
                    continue
                if p.is_symlink() or p.name.endswith((".tmp", ".part")):
                    continue
                all_paths.append((root, p))
                if len(all_paths) > max_files:
                    raise ValueError("SCAN_FILE_LIMIT_NO_CATALOG_WRITTEN")
    for root, path in all_paths:
        key = str(path).casefold()
        seen.add(key)
        prior = old_paths.get(key)
        try:
            stat = path.stat()
            unchanged = (
                prior
                and prior["size_bytes"] == stat.st_size
                and prior["mtime_ns"] == stat.st_mtime_ns
            )
            sha = (
                prior["sha256"] if prior is not None and unchanged and not verify else digest(path)
            )
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                raise ValueError("SOURCE_CHANGED_DURING_SCAN")
            # Reuse a missing prior identity on a hash-verified move. Copies get
            # separate resource IDs so rights from another location never transfer.
            if not prior:
                for candidate in old_hashes[(str(root), sha)]:
                    if (
                        candidate["id"] not in used_ids
                        and not Path(candidate["absolute_path"]).exists()
                    ):
                        prior = candidate
                        break
            moved = prior and prior["absolute_path"].casefold() != key
            changed = prior and prior["sha256"] != sha
            event = "moved" if moved else "changed" if changed else "unchanged" if prior else "new"
            events[event] += 1
            relative = path.relative_to(root).as_posix()
            category = CATEGORIES.get(
                relative.split("/")[0],
                "mba-corpus" if root.name == "mba-corpus" else "unclassified",
            )
            inspected = (
                {
                    k: prior[k]
                    for k in [
                        "pdf_pages",
                        "embedded_title",
                        "embedded_author",
                        "extraction",
                        "sampled_pdf_pages",
                        "sampled_alphanumeric_chars",
                    ]
                    if k in prior
                }
                if prior and unchanged
                else inspect_pdf(path)
                if path.suffix.lower() == ".pdf"
                else {
                    "extraction": "UNSUPPORTED_FORMAT"
                    if path.suffix.lower() == ".epub"
                    else "NOT_SAMPLED"
                }
            )
            title = inspected.get("embedded_title") or clean_title(path.stem)
            reviewed_metadata = bool(
                prior and prior.get("metadata_status") == "VERIFIED" and not changed
            )
            rights = (
                dict(prior["rights"])
                if prior
                else {
                    "local_possession": True,
                    "permission_status": "REVIEW_REQUIRED",
                    "permitted_uses": [],
                    "reviewed_at": None,
                    "evidence": None,
                }
            )
            if changed:
                rights.update(
                    permission_status="REVIEW_REQUIRED", permitted_uses=[], reviewed_at=None
                )
            row = {
                **(prior or {}),
                "id": prior["id"] if prior else str(uuid.uuid4()),
                "work_key_unverified": str(
                    uuid.uuid5(NAMESPACE, clean_title(path.stem).casefold())
                ),
                "absolute_path": str(path),
                "root": str(root),
                "relative_path": relative,
                "filename": path.name,
                "format": path.suffix.lower().lstrip("."),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                "sha256": sha,
                **inspected,
                "title": prior["title"] if reviewed_metadata and prior else title,
                "authors": prior["authors"]
                if reviewed_metadata and prior
                else [inspected["embedded_author"]]
                if inspected.get("embedded_author")
                else [],
                "metadata_status": "VERIFIED" if reviewed_metadata else "NEEDS_METADATA_REVIEW",
                "edition": None if changed else (prior or {}).get("edition"),
                "publication_year": None if changed else (prior or {}).get("publication_year"),
                "category": category,
                "tags": (prior or {}).get("tags", [category]),
                "collection": (prior or {}).get("collection")
                or (
                    "managed-mba-review"
                    if root.name == "mba-corpus"
                    else "social-systems"
                    if category == "social-systems"
                    else "personal-library"
                ),
                "access": (prior or {}).get("access", {"visibility": "PRIVATE", "owner_id": None}),
                "rights": rights,
                "presence": "PRESENT",
                "scan_event": event,
                "catalog_status": "NEEDS_PERMISSION_REVIEW"
                if rights["permission_status"] != "APPROVED"
                else "APPROVED",
                "ingestion": (prior or {}).get(
                    "ingestion", {"status": "CATALOGED", "indexed_revision": None}
                ),
            }
            if changed:
                row["ingestion"] = {**row["ingestion"], "source_changed": True}
            records.append(row)
            used_ids.add(row["id"])
            if progress and len(records) % 2000 == 0:
                atomic_json(
                    progress,
                    {
                        "schema_version": 1,
                        "resources": records,
                        "completed_files": len(records),
                        "discovered_files": len(all_paths),
                    },
                )
        except (OSError, ValueError):
            errors.append({"path": str(path), "code": "FILE_UNAVAILABLE_OR_CHANGED"})
            if prior:
                records.append({**prior, "presence": "UNAVAILABLE"})
                used_ids.add(prior["id"])
    for prior in old:
        if prior["id"] not in used_ids:
            if prior["root"] not in root_states:
                records.append({**prior, "scan_event": "not_scanned"})
                continue
            # A missing drive does not revoke/delete an indexed book.
            records.append({**prior, "presence": "MISSING_OR_UNAVAILABLE", "scan_event": "missing"})
            events["missing"] += 1
    return {
        "schema_version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "roots": root_states,
        "events": dict(events),
        "errors": errors,
        "resources": records,
        "virtual_books": previous.get("virtual_books", []),
    }


def generated_views(catalog: dict, output: Path):
    """Derived views only; library.json is the single metadata authority."""
    groups, similar = defaultdict(list), defaultdict(list)
    for row in catalog["resources"]:
        if row.get("sha256"):
            groups[row["sha256"]].append(row["id"])
        if row["format"] == "pdf":
            similar[clean_title(row["title"]).casefold()].append(row)
    exact = [{"sha256": h, "resource_ids": ids} for h, ids in groups.items() if len(ids) > 1]
    probable = [
        {
            "normalized_title": title,
            "resource_ids": [r["id"] for r in rows],
            "status": "UNVERIFIED_EDITION_OR_WORK_MATCH",
        }
        for title, rows in similar.items()
        if len({r.get("sha256") for r in rows}) > 1
    ]
    atomic_json(
        output / "duplicates.json",
        {"derived_from": "library.json", "exact": exact, "probable": probable},
    )
    plan = []
    for row in catalog["resources"]:
        if row["format"] != "pdf":
            continue
        title = clean_title(row["title"])
        proposed = re.sub(r'[<>:"/\\|?*]', "-", title)[:180].rstrip(" .") + ".pdf"
        target = Path(row["absolute_path"]).with_name(proposed)
        if target.name != row["filename"]:
            plan.append(
                {
                    "current_path": row["absolute_path"],
                    "proposed_path": str(target),
                    "sha256": row["sha256"],
                    "collision": target.exists(),
                    "reason": "Metadata/filename cleanup proposal; title and author require review",
                    "approval_required": True,
                }
            )
    atomic_json(output / "rename-plan.json", {"derived_from": "library.json", "proposals": plan})
    counts = Counter(r["format"] for r in catalog["resources"])
    categories = Counter(r["category"] for r in catalog["resources"])
    extraction = Counter(r.get("extraction") for r in catalog["resources"] if r["format"] == "pdf")
    report = (
        "# Local file inventory\n\nGenerated from `library.json`; source files were not moved, renamed or indexed.\n\n"
        f"Resources: {len(catalog['resources'])}. Formats: {dict(counts)}.\n\n"
        f"Categories: {dict(categories)}.\n\nPDF sample classifications: {dict(extraction)}.\n\n"
        f"Scan events: {catalog['events']}. Inaccessible/changed paths: {len(catalog['errors'])}.\n\n"
        "PDF classification samples at most three physical pages; it is not a full extraction guarantee.\n"
        "Embedded titles/authors and filename suggestions remain unverified metadata. No edition or publication year was inferred.\n"
    )
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "FILE_INVENTORY.md").write_text(report, encoding="utf-8")
    (reports / "DUPLICATE_REPORT.md").write_text(
        f"# Duplicates\n\n{len(exact)} exact SHA-256 groups; {len(probable)} probable title matches with different bytes.\n"
        "See `../duplicates.json` and resolve resource IDs through `../library.json`.\n"
        "No files were deleted or merged. Rights and access do not transfer between copies or editions.\n",
        encoding="utf-8",
    )
    (reports / "ORGANIZATION_PLAN.md").write_text(
        "# Organization plan\n\nKeep all existing locations. Seven numbered folders are subject categories, not separate vector databases.\n"
        "The existing mba-corpus remains authoritative for its source files; Knowledge/MBA and Social Systems remain separate catalog categories.\n"
        "No new source subdirectories, copies, shortcuts or junctions are proposed.\n"
        "`../rename-plan.json` is a proposal only. Verify titles/authors/editions and collisions before approving any rename.\n"
        "Metadata lacking evidence remains unknown. Files marked MISSING_OR_UNAVAILABLE are retained, not deleted or revoked.\n",
        encoding="utf-8",
    )


def refresh(roots: list[Path], output: Path, *, dry_run=False, verify=False):
    """Exclusive writer; atomic replacement prevents partial catalog refreshes."""
    if dry_run:
        return scan(roots, read_catalog(output / "library.json"), verify=verify)
    output.mkdir(parents=True, exist_ok=True)
    with catalog_lock(output):
        prior_path = output / "library.json"
        progress = output / "scan-progress.json"
        prior = read_catalog(prior_path if prior_path.exists() else progress)
        value = scan(roots, prior, verify=verify, progress=progress)
        atomic_json(output / "library.json", value)
        generated_views(value, output)
        progress.unlink(missing_ok=True)
        return value
