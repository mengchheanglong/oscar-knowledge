"""Index exact embedding input lookup without changing source rows or vectors."""

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.execute("CREATE INDEX ix_chunks_text_md5 ON chunks (md5(text))")


def downgrade():
    op.execute("DROP INDEX ix_chunks_text_md5")
