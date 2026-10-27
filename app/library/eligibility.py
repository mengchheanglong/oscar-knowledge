"""Current evidence eligibility shared by search and full-passage inspection."""

from sqlalchemy import and_, false, or_

from app.db.models import Chunk, Collection, Document, LibraryBook
from app.library.access import private_book_access


def current_source_conditions(settings, subject):
    shared = set(settings.allowed_collections) - set(settings.private_collections)
    private = set(settings.private_collections)
    public_access = and_(Collection.slug.in_(shared), Collection.visibility == "CURATED_SHARED")
    private_access = (
        and_(
            Collection.slug.in_(private),
            Collection.visibility == "PRIVATE",
            LibraryBook.visibility == "PRIVATE",
            private_book_access(subject, settings),
            Document.book_id.is_not(None),
        )
        if subject
        else false()
    )
    return [
        or_(public_access, private_access),
        Document.approved.is_(True),
        Document.status != "DELETED",
        Chunk.revision == Document.active_revision,
        Chunk.collection_id == Document.collection_id,
        or_(
            Document.book_id.is_(None),
            and_(
                LibraryBook.approved.is_(True),
                LibraryBook.status.in_(["INDEXED", "PARTIALLY_INDEXED"]),
                or_(
                    and_(LibraryBook.visibility == "CURATED_SHARED", public_access), private_access
                ),
                LibraryBook.collection_id == Document.collection_id,
                LibraryBook.active_generation == Document.book_generation,
            ),
        ),
        Chunk.id.not_in(settings.quality_excluded_chunk_ids),
    ]
