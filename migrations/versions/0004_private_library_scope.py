"""Permit private collections only after book ownership gates exist."""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.execute("""
    ALTER TABLE collections DROP CONSTRAINT collections_visibility_check;
    ALTER TABLE collections ADD CONSTRAINT collections_visibility_check
      CHECK (visibility IN ('CURATED_SHARED', 'PRIVATE'));
    ALTER TABLE library_books ADD CONSTRAINT library_books_scope_check CHECK (
      (visibility = 'PRIVATE' AND owner_id IS NOT NULL) OR
      (visibility = 'CURATED_SHARED' AND owner_id IS NULL));
    ALTER TABLE documents ADD CONSTRAINT documents_book_generation_check CHECK (
      (book_id IS NULL AND book_generation IS NULL) OR
      (book_id IS NOT NULL AND book_generation >= 1));
    """)


def downgrade():
    raise RuntimeError(
        "Retain private ownership constraints and data; disable private endpoints for rollback."
    )
