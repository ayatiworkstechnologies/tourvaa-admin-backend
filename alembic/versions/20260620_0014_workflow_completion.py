"""Workflow completion tables

Revision ID: 20260620_0014
Revises: 20260620_0013
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260620_0014"
down_revision = "20260620_0013"
branch_labels = None
depends_on = None


def _has_table(inspector, table):
    return table in inspector.get_table_names()


def _cols(inspector, table):
    if not _has_table(inspector, table):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "message_replies"):
        op.create_table(
            "message_replies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("communication_id", sa.Integer(), sa.ForeignKey("booking_communications.id"), nullable=False),
            sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("sender_type", sa.String(30), nullable=False, server_default="admin"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_message_replies_communication_id", "message_replies", ["communication_id"])

    if not _has_table(inspector, "email_logs"):
        op.create_table(
            "email_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recipient_email", sa.String(180), nullable=False),
            sa.Column("subject", sa.String(255), nullable=False),
            sa.Column("template_key", sa.String(100), nullable=True),
            sa.Column("entity_type", sa.String(60), nullable=True),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_email_logs_entity", "email_logs", ["entity_type", "entity_id"])

    if not _has_table(inspector, "notification_logs"):
        op.create_table(
            "notification_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=True),
            sa.Column("channel", sa.String(30), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("response", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_notification_logs_notification_id", "notification_logs", ["notification_id"])

    if not _has_table(inspector, "login_history"):
        op.create_table(
            "login_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("email", sa.String(150), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("failure_reason", sa.String(255), nullable=True),
            sa.Column("client_type", sa.String(30), nullable=False, server_default="web"),
            sa.Column("device_id", sa.String(120), nullable=True),
            sa.Column("device_name", sa.String(180), nullable=True),
            sa.Column("ip_address", sa.String(100), nullable=True),
            sa.Column("user_agent", sa.String(255), nullable=True),
            sa.Column("session_id", sa.String(120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_login_history_user_id", "login_history", ["user_id"])
        op.create_index("ix_login_history_email", "login_history", ["email"])

    user_cols = _cols(inspector, "users")
    if "two_factor_enabled" not in user_cols:
        op.add_column("users", sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "two_factor_secret" not in user_cols:
        op.add_column("users", sa.Column("two_factor_secret", sa.String(255), nullable=True))
    if "force_password_reset" not in user_cols:
        op.add_column("users", sa.Column("force_password_reset", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    inspector = inspect(op.get_bind())
    user_cols = _cols(inspector, "users")
    for col in ["force_password_reset", "two_factor_secret", "two_factor_enabled"]:
        if col in user_cols:
            op.drop_column("users", col)
    for table in ["login_history", "notification_logs", "email_logs", "message_replies"]:
        if _has_table(inspector, table):
            op.drop_table(table)
