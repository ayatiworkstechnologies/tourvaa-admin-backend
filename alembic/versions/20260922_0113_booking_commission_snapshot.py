"""Immutable commission-split snapshot on bookings.

Adds tourvaa_commission_percentage/amount, supplier_net_payable,
agent_commission_percentage/amount, affiliate_commission_percentage/amount
and tourvaa_net_revenue to bookings -- captured once at booking creation
(services.bookings._apply_commission_snapshot) per the confirmed
commission-deduction pricing model (no admin markup; agent/affiliate
commission is carved out of Tourvaa's own commission, not paid
additionally).

Revision ID: 20260922_0113
Revises: 20260922_0112
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0113"
down_revision = "20260922_0112"
branch_labels = None
depends_on = None

_NEW_COLUMNS = [
    ("tourvaa_commission_percentage", sa.Numeric(5, 2)),
    ("tourvaa_commission_amount", sa.Numeric(12, 2)),
    ("supplier_net_payable", sa.Numeric(12, 2)),
    ("agent_commission_percentage", sa.Numeric(5, 2)),
    ("agent_commission_amount", sa.Numeric(12, 2)),
    ("affiliate_commission_percentage", sa.Numeric(5, 2)),
    ("affiliate_commission_amount", sa.Numeric(12, 2)),
    ("tourvaa_net_revenue", sa.Numeric(12, 2)),
]


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    for name, coltype in _NEW_COLUMNS:
        if name not in cols:
            op.add_column("bookings", sa.Column(name, coltype, nullable=True))


def downgrade():
    pass
