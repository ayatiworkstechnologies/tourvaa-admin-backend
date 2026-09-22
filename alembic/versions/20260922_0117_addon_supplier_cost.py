"""Cost-plus per-item margin model: supplier_cost on optional
activities/accommodation extras/tour extensions, plus booking-level
cost-plus snapshots.

Adds supplier_cost (nullable, no default) to tour_optional_activities,
tour_accommodation_extras and tour_extensions -- when set, that item's
supplier is paid exactly quantity * supplier_cost with NO commission %
applied, and Tourvaa's margin is customer price minus that cost. NULL (the
default -- covers every existing row) means "no cost-plus margin
configured", falling back to the existing commissionable/commission-
percentage behavior exactly as before this column existed. Mutually
exclusive per item with the commissionable flag added in
20260922_0116_addon_commissionable_flag.py -- see
services.bookings._price_booking / compute_booking_supplier_financials.

Also adds Booking.cost_plus_customer_amount (the customer-price portion of
cost-plus line items, carved out of the commissionable base exactly like
non_commissionable_addon_amount) and Booking.cost_plus_supplier_payable
(what the supplier is actually owed for those same items, added back onto
gross_amount/net_payable). Both default to 0 so existing bookings (no
cost-plus items) are unaffected.

Revision ID: 20260922_0117
Revises: 20260922_0116
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0117"
down_revision = "20260922_0116"
branch_labels = None
depends_on = None

_ADDON_TABLES = [
    "tour_optional_activities",
    "tour_accommodation_extras",
    "tour_extensions",
]


def upgrade():
    bind = op.get_bind()

    for table in _ADDON_TABLES:
        cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        if "supplier_cost" not in cols:
            op.add_column(
                table,
                sa.Column("supplier_cost", sa.Numeric(12, 2), nullable=True),
            )

    booking_cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    if "cost_plus_customer_amount" not in booking_cols:
        op.add_column(
            "bookings",
            sa.Column("cost_plus_customer_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        )
    if "cost_plus_supplier_payable" not in booking_cols:
        op.add_column(
            "bookings",
            sa.Column("cost_plus_supplier_payable", sa.Numeric(12, 2), nullable=False, server_default="0"),
        )


def downgrade():
    pass
