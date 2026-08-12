"""Direct customer/agent <-> supplier messaging, scoped per booking.

Revision ID: 20260812_0063
Revises: 20260812_0062
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260812_0063"
down_revision = "20260812_0062"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "booking_conversations"):
        op.create_table(
            "booking_conversations",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
            sa.Column("initiator_role", sa.String(length=20), nullable=False),
            sa.Column("initiator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("supplier_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_message_preview", sa.String(length=300), nullable=True),
            sa.Column("initiator_unread_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("supplier_unread_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("booking_id", "initiator_user_id", "supplier_user_id", name="uq_booking_conv_parties"),
        )
        op.create_index("ix_booking_conversations_booking_id", "booking_conversations", ["booking_id"])
        op.create_index("ix_booking_conversations_initiator_user_id", "booking_conversations", ["initiator_user_id"])
        op.create_index("ix_booking_conversations_supplier_user_id", "booking_conversations", ["supplier_user_id"])
        op.create_index("ix_booking_conversations_last_message_at", "booking_conversations", ["last_message_at"])

    if not _has_table(inspector, "booking_messages"):
        op.create_table(
            "booking_messages",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("booking_conversations.id"), nullable=False),
            sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("sender_role", sa.String(length=20), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_booking_messages_conversation_id", "booking_messages", ["conversation_id"])
        op.create_index("ix_booking_messages_sender_user_id", "booking_messages", ["sender_user_id"])
        op.create_index("ix_booking_messages_created_at", "booking_messages", ["created_at"])


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "booking_messages"):
        op.drop_table("booking_messages")
    if _has_table(inspector, "booking_conversations"):
        op.drop_table("booking_conversations")
