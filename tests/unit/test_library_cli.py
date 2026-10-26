import json
from contextlib import nullcontext

from app.library.catalog import atomic_json, read_catalog
from app.library.cli import ingest_book
from app.library.cli import revoke_resource


def test_cli_ingestion_releases_metadata_lock_and_preserves_concurrent_revoke(
    tmp_path, monkeypatch
):
    row = {
        "id": "fixture",
        "sha256": "a" * 64,
        "rights": {"permission_status": "APPROVED"},
        "ingestion": {"status": "PROCESSING"},
    }
    atomic_json(tmp_path / "library.json", {"schema_version": 1, "resources": [row]})
    state = (
        tmp_path
        / "ingestion-cache"
        / row["id"]
        / row["sha256"]
        / "bookparts-v2"
        / "preparation.json"
    )
    atomic_json(state, {})

    def ingest(*args, **kwargs):
        assert not (tmp_path / ".catalog.lock").exists()
        value = read_catalog(tmp_path / "library.json")
        value["resources"][0]["rights"]["permission_status"] = "REVOKED"
        value["resources"][0]["ingestion"]["status"] = "REVOKED"
        atomic_json(tmp_path / "library.json", value)
        return {"status": "INDEXED", "generation": 1}

    monkeypatch.setattr("app.db.session.session", lambda: nullcontext(object()))
    monkeypatch.setattr("app.library.books.ingest_parts", ingest)
    ingest_book(
        "fixture",
        collection="personal-library",
        limit=10,
        allow_partial=False,
        catalog_dir=tmp_path,
    )
    result = json.loads((tmp_path / "library.json").read_text(encoding="utf-8"))
    assert result["resources"][0]["rights"]["permission_status"] == "REVOKED"
    assert result["resources"][0]["ingestion"]["status"] == "REVOKED"


def test_revoke_parent_cascades_to_derived_ranges_only(tmp_path, monkeypatch):
    def row(identifier, parent=None):
        return {
            "id": identifier,
            "parent_resource_id": parent,
            "rights": {"permission_status": "APPROVED", "permitted_uses": ["private_retrieval"]},
            "ingestion": {"status": "INDEXED"},
        }

    atomic_json(
        tmp_path / "library.json",
        {
            "schema_version": 1,
            "resources": [row("parent"), row("unrelated")],
            "virtual_books": [row("child", "parent"), row("grandchild", "child")],
        },
    )
    revoked = []
    monkeypatch.setattr("app.db.session.session", lambda: nullcontext(object()))
    monkeypatch.setattr(
        "app.library.books.revoke_book",
        lambda db, resource, settings: revoked.append(resource["id"]),
    )
    revoke_resource("parent", catalog_dir=tmp_path)
    assert set(revoked) == {"parent", "child", "grandchild"}
    value = read_catalog(tmp_path / "library.json")
    assert value["resources"][1]["rights"]["permission_status"] == "APPROVED"
    assert all(r["rights"]["permission_status"] == "REVOKED" for r in value["virtual_books"])
