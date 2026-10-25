import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(30), default="CURATED_SHARED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("collection_id", "canonical_key"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collections.id"), index=True)
    canonical_key: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500))
    institution: Mapped[str | None] = mapped_column(String(300))
    course_code: Mapped[str | None] = mapped_column(String(100), index=True)
    course_title: Mapped[str | None] = mapped_column(String(300))
    subject: Mapped[str | None] = mapped_column(String(100), index=True)
    content_type: Mapped[str] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(20), default="en")
    author: Mapped[str | None] = mapped_column(String(300))
    publication_year: Mapped[int | None] = mapped_column(Integer, index=True)
    license_type: Mapped[str] = mapped_column(String(100), default="USER_AUTHORIZED")
    license_url: Mapped[str | None] = mapped_column(Text)
    usage_notes: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(default=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    active_revision: Mapped[int] = mapped_column(default=0)
    parser_version: Mapped[str | None] = mapped_column(String(100))
    embedding_identity: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default="DISCOVERED", index=True)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "revision", "ordinal"),
        Index("ix_chunks_active", "collection_id", "document_id", "revision"),
        Index("ix_chunks_fts", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collections.id"))
    revision: Mapped[int] = mapped_column()
    ordinal: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column()
    token_estimate: Mapped[int] = mapped_column()
    heading_path: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column()
    page_end: Mapped[int | None] = mapped_column()
    start_ms: Mapped[int | None] = mapped_column()
    end_ms: Mapped[int | None] = mapped_column()
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_identity: Mapped[str | None] = mapped_column(String(300))
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    progress: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
