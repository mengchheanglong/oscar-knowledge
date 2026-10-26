import uuid
from pathlib import Path

import pymupdf

from app.library.catalog import refresh


def pdf(path: Path, text="Original systems feedback evidence"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as book:
        book.new_page().insert_text((50, 50), text)
        book.save(path)


def test_catalog_dry_run_duplicates_move_change_and_missing_drive(tmp_path):
    root = tmp_path / "Knowledge"
    output = root / "Catalog"
    p = root / "01-Strategy-and-Decision" / "systems.pdf"
    pdf(p)
    result = refresh([root], output, dry_run=True)
    assert not output.exists()
    assert result["resources"][0]["rights"]["permission_status"] == "REVIEW_REQUIRED"
    first = refresh([root], output)
    row = first["resources"][0]
    assert row["pdf_pages"] == 1 and row["category"] == "strategy-and-decision"
    assert row["access"]["visibility"] == "PRIVATE"
    assert row["ingestion"]["status"] == "CATALOGED"
    moved = p.with_name("renamed.pdf")
    p.rename(moved)
    second = refresh([root], output)
    assert second["resources"][0]["id"] == row["id"]
    assert second["events"] == {"moved": 1}
    copy = moved.with_name("copy.pdf")
    copy.write_bytes(moved.read_bytes())
    third = refresh([root], output)
    assert len({r["id"] for r in third["resources"]}) == 2
    import json

    assert len(json.loads((output / "duplicates.json").read_text())["exact"]) == 1
    assert len(refresh([root], output)["resources"]) == 2  # excludes its own output
    copy.unlink()
    missing = refresh([root], output)
    assert any(r["presence"] == "MISSING_OR_UNAVAILABLE" for r in missing["resources"])
    assert all(r["ingestion"]["status"] != "DELETED" for r in missing["resources"])


def test_changed_bytes_keep_id_but_invalidate_rights(tmp_path):
    from app.library.catalog import atomic_json

    root, out = tmp_path / "source", tmp_path / "catalog"
    root.mkdir()
    p = root / "notes.md"
    p.write_text("original material")
    catalog = refresh([root], out)
    row = catalog["resources"][0]
    row["rights"].update(permission_status="APPROVED", permitted_uses=["local_index"])
    row.update(edition="First edition", publication_year=2001, metadata_status="VERIFIED")
    atomic_json(out / "library.json", catalog)
    p.write_text("changed material with different bytes")
    updated = refresh([root], out)["resources"][0]
    assert updated["id"] == row["id"]
    assert updated["rights"]["permission_status"] == "REVIEW_REQUIRED"
    assert updated["rights"]["permitted_uses"] == []
    assert updated["edition"] is None and updated["publication_year"] is None
    assert updated["metadata_status"] == "NEEDS_METADATA_REVIEW"


def test_private_permission_is_separate_from_shared_permission(tmp_path):
    from app.library.books import require_shared_permission

    row = {
        "id": str(uuid.uuid4()),
        "sha256": "a" * 64,
        "format": "pdf",
        "presence": "PRESENT",
        "rights": {
            "permission_status": "APPROVED",
            "approved_sha256": "a" * 64,
            "evidence": "User authorized owned PDF private use",
            "permitted_uses": ["local_index", "private_retrieval"],
        },
        "access": {"visibility": "PRIVATE", "owner_id": str(uuid.uuid4())},
    }
    require_shared_permission(row)
    row["access"]["visibility"] = "CURATED_SHARED"
    import pytest

    with pytest.raises(ValueError, match="SOURCE_PERMISSION_REQUIRED"):
        require_shared_permission(row)


def test_subset_refresh_preserves_other_roots_and_reviewed_metadata(tmp_path):
    from app.library.catalog import atomic_json

    first, second, output = tmp_path / "one", tmp_path / "two", tmp_path / "catalog"
    first.mkdir()
    second.mkdir()
    (first / "note.md").write_text("first")
    (second / "note.md").write_text("second")
    value = refresh([first, second], output)
    row = next(r for r in value["resources"] if r["root"] == str(first))
    row.update(title="Reviewed title", authors=["Reviewed author"], metadata_status="VERIFIED")
    atomic_json(output / "library.json", value)
    updated = refresh([first], output)
    assert (
        next(r for r in updated["resources"] if r["id"] == row["id"])["title"] == "Reviewed title"
    )
    assert all(r["presence"] == "PRESENT" for r in updated["resources"])


def test_preparation_terminates_child_when_memory_budget_is_exceeded(tmp_path, monkeypatch):
    import pytest
    from app.library.books import prepare
    from app.library.catalog import digest

    path = tmp_path / "book.pdf"
    pdf(path)
    sha = digest(path)
    row = {
        "id": str(uuid.uuid4()),
        "sha256": sha,
        "format": "pdf",
        "presence": "PRESENT",
        "absolute_path": str(path),
        "rights": {
            "permission_status": "APPROVED",
            "approved_sha256": sha,
            "evidence": "Original test PDF",
            "permitted_uses": ["local_index", "private_retrieval"],
        },
        "access": {"visibility": "PRIVATE", "owner_id": str(uuid.uuid4())},
    }
    monkeypatch.setattr("app.library.limits.resident_bytes", lambda pid: 1024)
    with pytest.raises(ValueError, match="BOOK_PREPARATION_MEMORY_LIMIT"):
        prepare(row, tmp_path / "cache", memory_bytes=1)


def test_refresh_preserves_explicit_mba_private_collection_and_reuse_evidence(tmp_path):
    from app.library.catalog import atomic_json

    root, output = tmp_path / "mba-corpus", tmp_path / "catalog"
    pdf(root / "original.pdf")
    catalog = refresh([root], output)
    row = catalog["resources"][0]
    assert row["collection"] == "managed-mba-review"
    row["collection"] = "personal-library"
    row["mba_text_reuse"] = {"source_sha256": row["sha256"], "document_ids": [str(uuid.uuid4())]}
    atomic_json(output / "library.json", catalog)
    updated = refresh([root], output)["resources"][0]
    assert updated["collection"] == "personal-library"
    assert updated["mba_text_reuse"] == row["mba_text_reuse"]
    assert updated["id"] == row["id"]
