from dataclasses import replace

from app.ingestion.loaders import ExtractedSegment


def chunk_segments(segments: list[ExtractedSegment], max_chars=2400, overlap=360):
    """Segment boundaries retain exact locators. Long segments overlap, never cross pages."""
    if not 0 <= overlap < max_chars:
        raise ValueError("Invalid chunk overlap")
    merged: list[ExtractedSegment] = []
    for segment in segments:
        if merged:
            previous = merged[-1]
            same_section = (
                previous.heading_path == segment.heading_path
                and previous.page_start == segment.page_start
                and previous.page_end == segment.page_end
                and previous.metadata == segment.metadata
                and previous.start_ms is None
                and segment.start_ms is None
            )
            if same_section and len(previous.text) + len(segment.text) + 2 <= max_chars:
                merged[-1] = replace(previous, text=previous.text + "\n\n" + segment.text)
                continue
        merged.append(segment)
    for segment in merged:
        text = segment.text.strip()
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + max_chars // 2, end)
                if boundary > start:
                    end = boundary
            yield replace(
                segment,
                text=text[start:end],
                metadata={
                    **segment.metadata,
                    **(
                        {"review_required": "split_table"}
                        if segment.metadata.get("table") and len(text) > max_chars
                        else {}
                    ),
                },
            )
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
