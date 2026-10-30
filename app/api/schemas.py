from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: list[str] = Field(default_factory=list, max_length=20)
    course: list[str] = Field(default_factory=list, max_length=20)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    publication_year: list[int] = Field(default_factory=list, max_length=20)
    title: list[str] = Field(default_factory=list, max_length=20)
    author: list[str] = Field(default_factory=list, max_length=20)
    source_type: list[str] = Field(default_factory=list, max_length=20)


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    collection_ids: list[str] = Field(
        default_factory=lambda: ["mba-business"], min_length=1, max_length=10
    )
    top_k: int = Field(default=6, ge=1, le=20)
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    graph_expand: bool = True
    filters: Filters = Field(default_factory=Filters)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Query must contain text")
        return value.strip()


class Evidence(BaseModel):
    discovery_path: list[str] = Field(default_factory=list, max_length=5)
    extraction: str | None = None
    review_required: bool = False
    coverage_note: str | None = None
    book_id: UUID | None = None
    author: str | None = None
    edition: str | None = None
    chapter: str | None = None
    chunk_id: UUID
    document_id: UUID
    source_type: Literal["EXTERNAL_KNOWLEDGE"] = "EXTERNAL_KNOWLEDGE"
    collection_id: str
    title: str
    course_code: str | None
    institution: str | None
    locator: str | None
    locator_missing: bool
    page_start: int | None
    page_end: int | None
    start_ms: int | None
    end_ms: int | None
    source_url: str | None
    revision: int
    text: str
    snippet: str
    full_text_length: int | None = None
    is_truncated: bool = False
    rank: int
    score: float


class RetrievalResponse(BaseModel):
    fallback_reason: str | None = None
    retrieval_mode_used: Literal["keyword", "semantic", "hybrid"]
    score_semantics: str
    results: list[Evidence]


class GraphBrowseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection_ids: list[str] = Field(
        default_factory=lambda: ["mba-business"], min_length=1, max_length=10
    )
    query: str = Field(default="", max_length=200)
    topic_id: str | None = Field(default=None, max_length=80)
    source_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=40)
    offset: int = Field(default=0, ge=0, le=100000)


class PassageInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: UUID
    document_id: UUID
    revision: int = Field(ge=1)


class PassageInspectResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    collection_id: str
    title: str
    book_id: UUID | None = None
    author: str | None = None
    edition: str | None = None
    chapter: str | None = None
    locator: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    revision: int
    text: str = Field(max_length=100000)
    char_count: int
    extraction: str | None = None
    review_required: bool = False
    coverage_note: str | None = None
    source_url: str | None = None
    is_truncated: bool = False


class PassageWindowRequest(PassageInspectRequest):
    radius: int = Field(default=1, ge=0, le=2)
    max_chars: int = Field(default=12000, ge=1, le=16000)
    max_bytes: int = Field(default=48000, ge=1, le=64000)


class WindowPassage(PassageInspectResponse):
    relative_offset: int = Field(ge=-2, le=2)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_count: int = Field(ge=0)


class PassageWindowResponse(BaseModel):
    anchor_chunk_id: UUID
    document_id: UUID
    revision: int
    passages: list[WindowPassage] = Field(min_length=1, max_length=5)
    total_chars: int
    total_bytes: int
    context_limited: bool
