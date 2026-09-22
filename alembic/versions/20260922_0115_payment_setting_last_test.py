"""Add last connection-test result columns to payment_settings.

Supports the new POST /settings/payment/{provider}/test-connection endpoint,
which makes a real, side-effect-free auth check against Stripe/PayPal with
the currently configured credentials and persists the outcome here so the
admin UI can show "last checked" status without re-testing on every page
load.

Revision ID: 20260922_0115
Revises: 20260922_0114
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0115"
down_revision = "20260922_0114"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("last_test_status", sa.String(20)),
    ("last_test_at", sa.DateTime(timezone=True)),
    ("last_test_error", sa.Text()),
]


def upgrade():
    bind = op.get_bind()
    existing_cols = {c["name"] for c in sa.inspect(bind).get_columns("payment_settings")}
    for name, coltype in _COLUMNS:
        if name not in existing_cols:
            op.add_column("payment_settings", sa.Column(name, coltype, nullable=True))


def downgrade():
    pass
