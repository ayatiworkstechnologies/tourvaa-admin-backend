"""Add durable idempotent notification delivery reservations."""

from alembic import op
import sqlalchemy as sa

revision = "20261007_0017"
down_revision = "20261006_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("recipient_type", sa.String(40), nullable=False),
        sa.Column("recipient_email", sa.String(180), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_delivery_idempotency"),
    )
    for column in ("event_type", "entity_type", "entity_id", "status"):
        op.create_index(f"ix_notification_deliveries_{column}", "notification_deliveries", [column])


def downgrade():
    op.drop_table("notification_deliveries")
