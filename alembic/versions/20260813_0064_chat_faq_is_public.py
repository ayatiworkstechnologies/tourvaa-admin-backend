"""Add is_public to chat_faqs so admins can add AI-training Q&A that stays
out of the customer-facing FAQ list.

Revision ID: 20260813_0064
Revises: 20260812_0063
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260813_0064"
down_revision = "20260812_0063"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "chat_faqs", "is_public"):
        op.add_column(
            "chat_faqs",
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "chat_faqs", "is_public"):
        op.drop_column("chat_faqs", "is_public")
