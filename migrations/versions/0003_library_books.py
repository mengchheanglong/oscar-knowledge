"""Add an aggregate book activation gate; preserve every existing document/vector."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("""
    CREATE TABLE library_books (
      id uuid PRIMARY KEY,
      collection_id uuid NOT NULL REFERENCES collections(id),
      title varchar(500) NOT NULL,
      author varchar(300),
      edition varchar(200),
      approved boolean NOT NULL DEFAULT false,
      visibility varchar(30) NOT NULL DEFAULT 'PRIVATE',
      owner_id uuid,
      active_generation integer NOT NULL DEFAULT 0,
      source_sha256 varchar(64),
      status varchar(30) NOT NULL DEFAULT 'CATALOGED'
    );
    CREATE INDEX ix_library_books_collection_id ON library_books(collection_id);
    ALTER TABLE documents ADD COLUMN book_id uuid REFERENCES library_books(id);
    ALTER TABLE documents ADD COLUMN book_generation integer;
    CREATE INDEX ix_documents_book_id ON documents(book_id);
    """)


def downgrade():
    raise RuntimeError(
        "Retain additive book metadata. Roll back application only; do not drop indexed data."
    )
