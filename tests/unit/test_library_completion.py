import hashlib

import pymupdf
import pytest

from app.library.books import _prepare_pages
from app.library.books import preparation_folder
from app.library.source import fingerprint, verify_source
from scripts.complete_library import uncovered_windows


def test_non_text_completion_cannot_hide_unresolved_or_unprocessed_pages(tmp_path):
    from app.library.books import non_text_preparation

    path = tmp_path / "blank.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    row = {
        "id": "blank",
        "absolute_path": str(path),
        "pdf_pages": 1,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    state = _prepare_pages(row, tmp_path / "prepared", 10)
    assert non_text_preparation(row, state)
    state["ocr_required_pages"] = [1]
    assert not non_text_preparation(row, state)
    state["ocr_required_pages"] = []
    state["blank_pages"] = []
    assert not non_text_preparation(row, state)


def test_original_text_audit_cache_requires_prior_pass_same_source_and_part_checksum(tmp_path):
    from types import SimpleNamespace
    from app.library.catalog import atomic_json, digest
    from scripts.audit_prepared_books import prior_page_hashes

    path = tmp_path / "part.bookpart"
    atomic_json(
        path,
        {
            "metadata": {"extraction": "PDF_EMBEDDED_TEXT"},
            "pages": [{"page": 3, "text": "Original verified fixture"}],
        },
    )
    document = SimpleNamespace(local_path=str(path), active_revision=1)
    prior = {
        "status": "PASS",
        "proof": {"source_sha256": "source-sha", "parts": [["id", 1, digest(path)]]},
    }
    assert prior_page_hashes(prior, {"id": document}, "source-sha") == {
        3: hashlib.sha256(b"Original verified fixture").hexdigest()
    }
    assert not prior_page_hashes(prior, {"id": document}, "changed-source")
    prior["status"] = "FAIL"
    assert not prior_page_hashes(prior, {"id": document}, "source-sha")
    prior["status"] = "PASS"
    path.write_text("changed prepared bytes")
    assert not prior_page_hashes(prior, {"id": document}, "source-sha")


def test_final_pdf_gate_rejects_stale_source_or_grant_even_if_old_book_is_indexed():
    from scripts.audit_library_coverage import original_pdf_complete

    row = {
        "sha256": "current",
        "rights": {"permission_status": "APPROVED", "approved_sha256": "current"},
        "ingestion": {"status": "INDEXED", "source_sha256": "current"},
    }
    assert original_pdf_complete(row)
    row["sha256"] = "changed-source"
    assert not original_pdf_complete(row)
    row["sha256"] = "current"
    row["rights"]["permission_status"] = "REVOKED"
    assert not original_pdf_complete(row)


def test_physical_windows_cover_every_page_once_and_reject_overlap():
    selected = [[11, 25], [49, 70]]
    windows = uncovered_windows(100, selected, size=10)
    pages = [p for first, last in selected + windows for p in range(first, last + 1)]
    assert sorted(pages) == list(range(1, 101))
    assert all(last - first < 10 for first, last in windows)
    with pytest.raises(ValueError, match="OVERLAP"):
        uncovered_windows(100, [[5, 20], [15, 30]])


def test_source_hash_reuse_invalidates_when_stat_identity_changes(tmp_path, monkeypatch):
    path = tmp_path / "original.txt"
    path.write_text("original")
    resource = {"absolute_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    calls = []

    def counted_digest(p):
        calls.append(p)
        return hashlib.sha256(p.read_bytes()).hexdigest()

    monkeypatch.setattr("app.library.source.digest", counted_digest)
    first = verify_source(resource)
    assert verify_source(resource) == first and len(calls) == 1
    path.write_text("changed bytes")
    with pytest.raises(ValueError, match="CHECKSUM"):
        verify_source(resource)
    assert len(calls) == 2


def test_reviewed_non_text_and_visual_transcription_are_explicit_and_hash_bound(tmp_path):
    path = tmp_path / "original.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().draw_line((50, 50), (500, 50))
        pdf.new_page().insert_text((50, 50), "Original fixture title")
        pdf.save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    resource = {
        "id": "fixture",
        "absolute_path": str(path),
        "sha256": sha,
        "page_reviews": {
            "1": {"classification": "NON_TEXT_DECORATION", "source_sha256": sha},
            "2": {
                "classification": "VISUALLY_REVIEWED_TRANSCRIPTION",
                "extraction": "VISUALLY_REVIEWED_TRANSCRIPTION",
                "source_sha256": sha,
                "text": "Original fixture title",
            },
        },
    }
    state = _prepare_pages(resource, tmp_path / "prepared", 10)
    assert state["complete"] and state["reviewed_non_text_pages"] == [1]
    assert not state["ocr_required_pages"]
    resource["page_reviews"]["1"]["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="PAGE_REVIEW_CHECKSUM"):
        _prepare_pages(resource, tmp_path / "other", 10)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        _prepare_pages(
            resource, tmp_path / "third", 10, verified_stat=(0,) * len(fingerprint(path))
        )


def test_empty_ocr_preserves_existing_short_embedded_text(tmp_path, monkeypatch):
    path = tmp_path / "footer.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 50), "Index 967")
        pdf.save(path)
    original = pymupdf.Page.get_text
    monkeypatch.setattr(pymupdf.Page, "get_textpage_ocr", lambda self, **kwargs: object())
    monkeypatch.setattr(
        pymupdf.Page,
        "get_text",
        lambda self, *args, **kwargs: ""
        if "textpage" in kwargs
        else original(self, *args, **kwargs),
    )
    row = {
        "id": "fixture",
        "absolute_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "ocr_tessdata": "fixture",
    }
    state = _prepare_pages(row, tmp_path / "prepared", 10)
    assert state["parts"] and not state["ocr_pages"] and not state["ocr_required_pages"]


def test_preparation_revisions_have_separate_bounded_cache_locations(tmp_path):
    row = {"id": "fixture", "sha256": "a" * 64, "preparation_version": 3}
    first = preparation_folder(tmp_path, row)
    row["preparation_revision"] = 1
    assert preparation_folder(tmp_path, row) != first
    row["preparation_revision"] = 101
    with pytest.raises(ValueError, match="PREPARATION_REVISION"):
        preparation_folder(tmp_path, row)


def test_active_preparation_finds_committed_revision_when_new_review_is_staged(tmp_path):
    from app.library.books import preparation_identity
    from app.library.catalog import atomic_json
    from app.library.status import active_preparation

    row = {"id": "fixture", "sha256": "a" * 64, "preparation_version": 3, "preparation_revision": 2}
    root = tmp_path / "ingestion-cache" / row["id"] / row["sha256"]
    states = []
    for revision in range(3):
        state = {
            "complete": True,
            "parts": [{"first_page": 1, "last_page": 1, "sha256": str(revision) * 64}],
        }
        atomic_json(root / f"bookparts-v3-r{revision}" / "preparation.json", state)
        states.append(state)
    path, state = active_preparation(
        tmp_path,
        row,
        preparation_identity(states[1]),
        row["sha256"],
        root / "bookparts-v3-r0" / "reused.bookpart",
    )
    assert path.parent.name == "bookparts-v3-r1" and state == states[1]
