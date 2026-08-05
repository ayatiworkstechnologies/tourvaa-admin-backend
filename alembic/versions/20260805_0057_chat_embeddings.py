"""RAG: chat_embeddings vector index for tours and FAQs

Revision ID: 20260805_0057
Revises: 20260804_0056
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260805_0057"
down_revision = "20260804_0056"
branch_labels = None
depends_on = None


def _has_table(inspector, table):
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "chat_embeddings"):
        op.create_table(
            "chat_embeddings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_type", sa.String(20), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("content_text", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("embedding", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_chat_embeddings_source_type", "chat_embeddings", ["source_type"])
        op.create_index("ix_chat_embeddings_source_id", "chat_embeddings", ["source_id"])
        op.create_unique_constraint(
            "uq_chat_embeddings_source", "chat_embeddings", ["source_type", "source_id"]
        )


def downgrade():
    op.drop_table("chat_embeddings")
