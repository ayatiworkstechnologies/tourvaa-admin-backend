"""Chatbot: per-message thumbs up/down feedback

Revision ID: 20260813_0065
Revises: 20260813_0064
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260813_0065"
down_revision = "20260813_0064"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "chat_feedback"):
        op.create_table(
            "chat_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id"), nullable=False, unique=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_chat_feedback_message_id", "chat_feedback", ["message_id"], unique=True)
        op.create_index("ix_chat_feedback_session_id", "chat_feedback", ["session_id"])


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "chat_feedback"):
        op.drop_table("chat_feedback")
