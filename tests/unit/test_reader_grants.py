import json
import uuid
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.library.access import can_read_private_book, grants_for


def test_exact_reader_owner_book_and_collection_binding_and_revocation(tmp_path):
    owner, reader, book_id = (uuid.uuid4() for _ in range(3))
    path = tmp_path / "readers.json"
    payload = {
        "version": 1,
        "grants": [
            {
                "reader_id": str(reader),
                "owner_id": str(owner),
                "book_ids": [str(book_id)],
                "collections": ["personal-library"],
            }
        ],
    }
    path.write_text(json.dumps(payload))
    settings = Settings(private_reader_grants_path=str(path))
    book = SimpleNamespace(id=book_id, owner_id=owner)
    assert can_read_private_book(book, "personal-library", str(owner), settings)
    assert can_read_private_book(book, "personal-library", str(reader), settings)
    assert not can_read_private_book(book, "personal-library", str(uuid.uuid4()), settings)
    assert not can_read_private_book(book, "social-systems", str(reader), settings)
    assert not can_read_private_book(
        SimpleNamespace(id=uuid.uuid4(), owner_id=owner), "personal-library", str(reader), settings
    )
    assert not can_read_private_book(
        SimpleNamespace(id=book_id, owner_id=uuid.uuid4()),
        "personal-library",
        str(reader),
        settings,
    )
    path.write_text(json.dumps({"version": 1, "grants": []}))
    assert not can_read_private_book(book, "personal-library", str(reader), settings)
    assert can_read_private_book(book, "personal-library", str(owner), settings)


@pytest.mark.parametrize(
    "content",
    [
        '{"version":1,"grants":[{"reader_id":"invalid"}]}',
        '{"version":2,"grants":[]}',
        '{"version":1,"grants":[],"wildcard":true}',
        "not json",
    ],
)
def test_invalid_manifests_fail_closed_without_private_details(tmp_path, content):
    path = tmp_path / "private-path.json"
    path.write_text(content)
    with pytest.raises(ValueError, match="^PRIVATE_READER_GRANTS_UNAVAILABLE$"):
        grants_for(str(uuid.uuid4()), Settings(private_reader_grants_path=str(path)))


def test_no_manifest_preserves_owner_only_access():
    owner, reader = uuid.uuid4(), uuid.uuid4()
    book = SimpleNamespace(id=uuid.uuid4(), owner_id=owner)
    settings = Settings(private_reader_grants_path="")
    assert can_read_private_book(book, "personal-library", str(owner), settings)
    assert not can_read_private_book(book, "personal-library", str(reader), settings)
