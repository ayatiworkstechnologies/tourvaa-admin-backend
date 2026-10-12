"""track browser-push deliveries and subscription health

Revision ID: 20261012_0025
Revises: 20261012_0024
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261012_0025"
down_revision = "20261012_0024"
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table):
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    notification_columns = _columns(bind, "notifications")
    if "event_key" not in notification_columns:
        op.add_column("notifications", sa.Column("event_key", sa.String(length=100), nullable=True))
    if "event_version" not in notification_columns:
        op.add_column("notifications", sa.Column("event_version", sa.String(length=100), nullable=True))
    if "idempotency_key" not in notification_columns:
        op.add_column("notifications", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    notification_indexes = _indexes(bind, "notifications")
    if "ix_notifications_event_key" not in notification_indexes:
        op.create_index("ix_notifications_event_key", "notifications", ["event_key"])
    if "uq_notifications_idempotency_key" not in {item["name"] for item in sa.inspect(bind).get_unique_constraints("notifications")}:
        op.create_unique_constraint("uq_notifications_idempotency_key", "notifications", ["idempotency_key"])

    subscription_columns = _columns(bind, "push_subscriptions")
    for name, column in (
        ("platform", sa.Column("platform", sa.String(length=20), nullable=True)),
        ("device_type", sa.Column("device_type", sa.String(length=30), nullable=True)),
        ("is_active", sa.Column("is_active", sa.Integer(), nullable=False, server_default="1")),
        ("last_used_at", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)),
        ("updated_at", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        if name not in subscription_columns:
            op.add_column("push_subscriptions", column)
    if "ix_push_subscriptions_is_active" not in _indexes(bind, "push_subscriptions"):
        op.create_index("ix_push_subscriptions_is_active", "push_subscriptions", ["is_active"])

    if not sa.inspect(bind).has_table("push_delivery_logs"):
        op.create_table(
            "push_delivery_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True),
            sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("push_subscriptions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_key", sa.String(length=100), nullable=True),
            sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider", sa.String(length=30), nullable=False, server_default="web_push"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_push_delivery_logs_notification_id", "push_delivery_logs", ["notification_id"])
        op.create_index("ix_push_delivery_logs_subscription_id", "push_delivery_logs", ["subscription_id"])
        op.create_index("ix_push_delivery_logs_event_key", "push_delivery_logs", ["event_key"])
        op.create_index("ix_push_delivery_logs_recipient_user_id", "push_delivery_logs", ["recipient_user_id"])
        op.create_index("ix_push_delivery_logs_status", "push_delivery_logs", ["status"])


def downgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("push_delivery_logs"):
        op.drop_table("push_delivery_logs")
    indexes = _indexes(bind, "push_subscriptions")
    if "ix_push_subscriptions_is_active" in indexes:
        op.drop_index("ix_push_subscriptions_is_active", table_name="push_subscriptions")
    for name in ("updated_at", "last_used_at", "is_active", "device_type", "platform"):
        if name in _columns(bind, "push_subscriptions"):
            op.drop_column("push_subscriptions", name)
    if "uq_notifications_idempotency_key" in {item["name"] for item in sa.inspect(bind).get_unique_constraints("notifications")}:
        op.drop_constraint("uq_notifications_idempotency_key", "notifications", type_="unique")
    if "ix_notifications_event_key" in _indexes(bind, "notifications"):
        op.drop_index("ix_notifications_event_key", table_name="notifications")
    for name in ("idempotency_key", "event_version", "event_key"):
        if name in _columns(bind, "notifications"):
            op.drop_column("notifications", name)
