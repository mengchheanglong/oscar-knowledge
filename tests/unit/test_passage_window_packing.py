import hashlib
import uuid

import pytest

from app.api.schemas import PassageInspectResponse, PassageWindowRequest
from app.retrieval.passage_window import pack_window


def passage(text, chunk_id=None, document_id=None):
    return PassageInspectResponse(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        collection_id="synthetic",
        title="Synthetic",
        revision=1,
        text=text,
        char_count=len(text),
    )


def test_windows_keep_original_unicode_spans_and_individual_hashes():
    anchor = passage("ខ្មែរ😀∑ = 12")
    neighbor = passage("Assumes constant cost.", document_id=anchor.document_id)
    request = PassageWindowRequest(
        chunk_id=anchor.chunk_id, document_id=anchor.document_id, revision=1
    )
    result = pack_window(request, [(anchor, 0), (neighbor, -1)])
    assert [p.text for p in result.passages] == [neighbor.text, anchor.text]
    assert result.total_chars == len(anchor.text) + len(neighbor.text)
    assert result.total_bytes == len((anchor.text + neighbor.text).encode("utf-8"))
    assert result.passages[1].text_sha256 == hashlib.sha256(anchor.text.encode()).hexdigest()
    assert all(not p.is_truncated for p in result.passages)


def test_whole_spans_omitted_when_byte_or_character_budget_cannot_fit():
    anchor = passage("😀")
    neighbor = passage("abcd", document_id=anchor.document_id)
    request = PassageWindowRequest(
        chunk_id=anchor.chunk_id, document_id=anchor.document_id, revision=1, max_bytes=4
    )
    result = pack_window(request, [(anchor, 0), (neighbor, 1)])
    assert len(result.passages) == 1 and result.context_limited
    with pytest.raises(ValueError, match="ANCHOR_TOO_LARGE"):
        pack_window(request.model_copy(update={"max_bytes": 3}), [(anchor, 0)])
    with pytest.raises(ValueError, match="ANCHOR_TOO_LARGE"):
        pack_window(
            request.model_copy(update={"max_chars": 1}),
            [(passage("ab", anchor.chunk_id, anchor.document_id), 0)],
        )


def test_serialized_response_limit_applies_to_escaped_text_too():
    anchor = passage("\x00" * 8000)
    neighbor = passage("\x00" * 8000, document_id=anchor.document_id)
    request = PassageWindowRequest(
        chunk_id=anchor.chunk_id,
        document_id=anchor.document_id,
        revision=1,
        max_chars=16000,
        max_bytes=64000,
    )
    result = pack_window(request, [(anchor, 0), (neighbor, 1)])
    assert len(result.model_dump_json().encode()) <= 96000
    assert result.context_limited and len(result.passages) == 1
