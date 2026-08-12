"""Admin <-> agent/supplier/customer messaging: conversations + messages.

Revision ID: 20260812_0062
Revises: 20260812_0061
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260812_0062"
down_revision = "20260812_0061"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "conversations"):
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("participant_type", sa.String(length=20), nullable=False),
            sa.Column("participant_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_message_preview", sa.String(length=300), nullable=True),
            sa.Column("admin_unread_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("participant_unread_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("participant_user_id", name="uq_conversation_participant_user"),
        )
        op.create_index("ix_conversations_participant_type", "conversations", ["participant_type"])
        op.create_index("ix_conversations_participant_user_id", "conversations", ["participant_user_id"])
        op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])

    if not _has_table(inspector, "messages"):
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("sender_role", sa.String(length=20), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
        op.create_index("ix_messages_sender_user_id", "messages", ["sender_user_id"])
        op.create_index("ix_messages_created_at", "messages", ["created_at"])


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "messages"):
        op.drop_table("messages")
    if _has_table(inspector, "conversations"):
        op.drop_table("conversations")
