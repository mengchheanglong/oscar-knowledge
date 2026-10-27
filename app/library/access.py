"""Explicit local read grants; never impersonate the authenticated subject."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, false, or_

from app.db.models import Collection, LibraryBook


class ReaderGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reader_id: UUID
    owner_id: UUID
    book_ids: tuple[UUID, ...] = Field(min_length=1, max_length=5000)
    collections: tuple[Literal["personal-library", "social-systems"], ...] = Field(
        min_length=1, max_length=2
    )


class ReaderGrants(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1]
    grants: tuple[ReaderGrant, ...] = Field(max_length=16)


def grants_for(subject, settings=None):
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    path = settings.private_reader_grants_path
    if not path or not subject:
        return ()
    try:
        source = Path(path)
        if not source.is_absolute() or source.stat().st_size > 1_048_576:
            raise ValueError
        manifest = ReaderGrants.model_validate_json(source.read_bytes())
        reader = UUID(str(subject))
        return tuple(grant for grant in manifest.grants if grant.reader_id == reader)
    except Exception:
        # No paths, identities, manifest contents or SQL in public errors.
        raise ValueError("PRIVATE_READER_GRANTS_UNAVAILABLE") from None


def private_book_access(subject, settings):
    if not subject:
        return false()
    clauses = [LibraryBook.owner_id == UUID(str(subject))]
    for grant in grants_for(subject, settings):
        clauses.append(
            and_(
                LibraryBook.owner_id == grant.owner_id,
                LibraryBook.id.in_(grant.book_ids),
                Collection.slug.in_(grant.collections),
            )
        )
    return or_(*clauses)


def can_read_private_book(book, collection, subject, settings=None):
    if not subject:
        return False
    if str(book.owner_id) == str(subject):
        return True
    return any(
        book.owner_id == grant.owner_id
        and book.id in grant.book_ids
        and collection in grant.collections
        for grant in grants_for(subject, settings)
    )
