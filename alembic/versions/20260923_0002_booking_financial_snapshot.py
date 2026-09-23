"""Full booking financial snapshot (price source, resolved unit prices,
group-discount base, commission base, discount funding split, channel
commission bases, lock timestamp).

Makes the money split captured at booking creation self-contained, so
supplier/agent/affiliate ledgers, the admin breakdown and reports read the
booking row instead of re-deriving money from the tour's current slab,
date price or commission settings. See
services.bookings.compute_booking_financial_split / _apply_commission_snapshot.

All columns are nullable: bookings created before this revision have no
snapshot and are locked (from their own stored amounts) the first time a
supplier accepts them.

Revision ID: 20260923_0002
Revises: 20260923_0001
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0002"
down_revision = "20260923_0001"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("price_source", sa.String(20)),
    ("date_price_id", sa.Integer()),
    ("adult_unit_price", sa.Numeric(12, 2)),
    ("child_unit_price", sa.Numeric(12, 2)),
    ("infant_unit_price", sa.Numeric(12, 2)),
    ("single_supplement_amount", sa.Numeric(12, 2)),
    ("group_discount_base_amount", sa.Numeric(12, 2)),
    ("group_discount_percentage", sa.Numeric(7, 4)),
    ("commission_base_amount", sa.Numeric(12, 2)),
    ("supplier_gross_amount", sa.Numeric(12, 2)),
    ("supplier_discount_share_amount", sa.Numeric(12, 2)),
    ("tourvaa_discount_share_amount", sa.Numeric(12, 2)),
    ("tourvaa_gross_revenue", sa.Numeric(12, 2)),
    ("agent_commission_base_amount", sa.Numeric(12, 2)),
    ("affiliate_commission_base_amount", sa.Numeric(12, 2)),
    ("financials_locked_at", sa.DateTime(timezone=True)),
]


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    for name, coltype in _COLUMNS:
        if name not in cols:
            op.add_column("bookings", sa.Column(name, coltype, nullable=True))


def downgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    for name, _coltype in reversed(_COLUMNS):
        if name in cols:
            op.drop_column("bookings", name)
