"""Track complete prepared-part identity independently from original PDF bytes."""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.execute("ALTER TABLE library_books ADD COLUMN preparation_sha256 varchar(64)")


def downgrade():
    raise RuntimeError("Retain additive preparation identity and existing evidence.")
