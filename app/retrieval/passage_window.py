"""Pack original chunks; never concatenate, summarize or silently clip source text."""

import hashlib

from app.api.schemas import PassageWindowRequest, PassageWindowResponse, WindowPassage


def pack_window(body: PassageWindowRequest, candidates, limited=False):
    selected: list[WindowPassage] = []
    chars = byte_count = 0
    # Caller supplies anchor first, then nearest permitted neighbors.
    for passage, offset in candidates:
        if (
            passage.document_id != body.document_id
            or passage.revision != body.revision
            or passage.char_count != len(passage.text)
            or abs(offset) > body.radius
            or any(p.chunk_id == passage.chunk_id or p.relative_offset == offset for p in selected)
        ):
            raise ValueError("WINDOW_SCOPE_MISMATCH")
        size = len(passage.text.encode("utf-8"))
        if chars + len(passage.text) > body.max_chars or byte_count + size > body.max_bytes:
            if not selected:
                raise ValueError("WINDOW_ANCHOR_TOO_LARGE")
            limited = True
            continue
        item = WindowPassage(
            **{**passage.model_dump(), "is_truncated": False},
            relative_offset=offset,
            text_sha256=hashlib.sha256(passage.text.encode("utf-8")).hexdigest(),
            byte_count=size,
        )
        selected.append(item)
        chars += len(passage.text)
        byte_count += size
    if not selected or selected[0].chunk_id != body.chunk_id:
        raise ValueError("WINDOW_ANCHOR_REQUIRED")

    def response():
        return PassageWindowResponse(
            anchor_chunk_id=body.chunk_id,
            document_id=body.document_id,
            revision=body.revision,
            passages=sorted(selected, key=lambda p: p.relative_offset),
            total_chars=sum(p.char_count for p in selected),
            total_bytes=sum(p.byte_count for p in selected),
            context_limited=limited,
        )

    result = response()
    while len(result.model_dump_json().encode("utf-8")) > 96000:
        if len(selected) == 1:
            raise ValueError("WINDOW_ANCHOR_TOO_LARGE")
        selected.pop()
        limited = True
        result = response()
    return result
