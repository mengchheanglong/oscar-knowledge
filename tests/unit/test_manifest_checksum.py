import hashlib

import pytest

from app.config import Settings
from app.ingestion.manifest import download, import_manifest


def test_pinned_download_reuses_identical_bytes_without_http_and_preserves_changed_file(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *args: pytest.fail("Pinned local cache must work offline")
    )
    path = tmp_path / "lecture.pdf"
    path.write_bytes(b"original authorized file")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    download("https://ocw.mit.edu/lecture.pdf", path, Settings(), digest)
    path.write_bytes(b"curator replacement")
    with pytest.raises(ValueError, match="DOWNLOAD_CHECKSUM_MISMATCH"):
        download("https://ocw.mit.edu/lecture.pdf", path, Settings(), digest)
    assert path.read_bytes() == b"curator replacement"


def test_hash_pin_does_not_approve_a_discovered_source(tmp_path, monkeypatch):
    import yaml

    path = tmp_path / "review.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "entries": [
                    {
                        "institution": "MIT",
                        "course_code": "test",
                        "course_title": "Review only",
                        "subject": "Test",
                        "course_page": "https://ocw.mit.edu/course/",
                        "download_url": "https://ocw.mit.edu/lecture.pdf",
                        "license": "Review required",
                        "sha256": "a" * 64,
                        "approved": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.ingestion.manifest.download", lambda *args: pytest.fail("Unapproved source downloaded")
    )
    assert import_manifest(None, path, Settings(), download_approved=True) == []
