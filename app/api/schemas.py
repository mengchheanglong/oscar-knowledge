from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: list[str] = Field(default_factory=list, max_length=20)
    course: list[str] = Field(default_factory=list, max_length=20)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    publication_year: list[int] = Field(default_factory=list, max_length=20)


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    collection_ids: list[str] = Field(
        default_factory=lambda: ["mba-business"], min_length=1, max_length=10
    )
    top_k: int = Field(default=6, ge=1, le=20)
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    filters: Filters = Field(default_factory=Filters)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Query must contain text")
        return value.strip()


class Evidence(BaseModel):
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
    rank: int
    score: float


class RetrievalResponse(BaseModel):
    retrieval_mode_used: Literal["keyword", "semantic", "hybrid"]
    score_semantics: str
    results: list[Evidence]
