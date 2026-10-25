"""Add model embeddings without changing chunks or the legacy vector column."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("""
    CREATE TABLE chunk_embeddings (
      chunk_id uuid NOT NULL REFERENCES chunks(id),
      identity varchar(300) NOT NULL,
      dimensions integer NOT NULL,
      embedding_1024 vector(1024),
      embedding_1536 vector(1536),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(chunk_id, identity),
      CONSTRAINT ck_embedding_dimension CHECK (
        (dimensions=1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL) OR
        (dimensions=1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL)
      )
    );
    CREATE INDEX ix_chunk_embeddings_identity ON chunk_embeddings(identity, chunk_id);
    """)


def downgrade():
    raise RuntimeError(
        "Non-destructive rollback: disable embeddings or use the prior application; retain this additive table"
    )
