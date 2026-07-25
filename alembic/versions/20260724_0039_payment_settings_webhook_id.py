"""add payment_settings.webhook_id

Needed to verify PayPal webhook signatures server-side (PayPal's
verify-webhook-signature API requires the webhook_id configured in the
merchant's PayPal developer dashboard). Stripe already verifies webhooks via
HMAC using its own secret_key-derived secret and does not need this column,
but it is generic across providers so both rows get it.

Revision ID: 20260724_0039
Revises: 20260724_0038
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0039"
down_revision = "20260724_0038"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("payment_settings", "webhook_id"):
        op.add_column("payment_settings", sa.Column("webhook_id", sa.String(length=150), nullable=True))


def downgrade():
    if _has_column("payment_settings", "webhook_id"):
        op.drop_column("payment_settings", "webhook_id")
