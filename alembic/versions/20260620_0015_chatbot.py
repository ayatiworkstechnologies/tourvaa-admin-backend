"""Chatbot: FAQs, sessions, messages

Revision ID: 20260620_0015
Revises: 20260620_0014
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260620_0015"
down_revision = "20260620_0014"
branch_labels = None
depends_on = None


def _has_table(inspector, table):
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "chat_faqs"):
        op.create_table(
            "chat_faqs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("question", sa.String(500), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("category", sa.String(100), nullable=False, server_default="general"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_chat_faqs_category", "chat_faqs", ["category"])

    if not _has_table(inspector, "chat_sessions"):
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_key", sa.String(64), nullable=False, unique=True),
            sa.Column("user_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("user_email", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_chat_sessions_session_key", "chat_sessions", ["session_key"])

    if not _has_table(inspector, "chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])


def downgrade():
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("chat_faqs")
