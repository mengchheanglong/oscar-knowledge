"""Add a derived, passage-anchored discovery graph; source/vector rows unchanged."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"


def upgrade():
    op.create_table(
        "graph_topics",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("domain", sa.String(80), nullable=False),
    )
    op.create_table(
        "graph_passage_topics",
        sa.Column(
            "chunk_id",
            postgresql.UUID(),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("topic_id", sa.String(80), sa.ForeignKey("graph_topics.id"), primary_key=True),
        sa.Column("extractor_version", sa.String(40), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("anchor_start", sa.Integer(), nullable=False),
        sa.Column("anchor_end", sa.Integer(), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
    )
    op.create_index("ix_graph_topic_chunk", "graph_passage_topics", ["topic_id", "chunk_id"])
    op.create_table(
        "graph_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extractor_version", sa.String(40), nullable=False),
        sa.Column(
            "built_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("scanned_chunks", sa.Integer(), nullable=False),
        sa.Column("mapped_chunks", sa.Integer(), nullable=False),
        sa.Column("links", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("graph_state")
    op.drop_table("graph_passage_topics")
    op.drop_table("graph_topics")
