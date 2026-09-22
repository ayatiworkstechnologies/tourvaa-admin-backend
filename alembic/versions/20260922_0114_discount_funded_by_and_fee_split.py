"""Discount funded_by (SUPPLIER/TOURVAA) + granular service/gateway fee columns.

Adds funded_by to tour_discounts (promo codes) and
tour_group_discount_tiers (group discounts), defaulting existing/new rows to
"SUPPLIER" so current behavior is unchanged unless explicitly set to
"TOURVAA" -- see services.bookings.compute_booking_supplier_financials,
which zeroes the group-discount ratio applied to the supplier's raw share
when the discount actually used on a booking was TOURVAA-funded.

Also adds the immutable per-booking snapshot of which funding mode was used
(group_discount_funded_by/promo_discount_funded_by), and splits
Booking.surcharge_amount's components out into their own columns
(service_fee_amount/gateway_fee_amount) without touching surcharge_amount
itself, which stays as the existing sum for backward compatibility.

Revision ID: 20260922_0114
Revises: 20260922_0113
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0114"
down_revision = "20260922_0113"
branch_labels = None
depends_on = None

_BOOKING_COLUMNS = [
    ("group_discount_funded_by", sa.String(20)),
    ("promo_discount_funded_by", sa.String(20)),
    ("service_fee_amount", sa.Numeric(12, 2)),
    ("gateway_fee_amount", sa.Numeric(12, 2)),
]


def upgrade():
    bind = op.get_bind()

    booking_cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    for name, coltype in _BOOKING_COLUMNS:
        if name not in booking_cols:
            op.add_column("bookings", sa.Column(name, coltype, nullable=True))

    discount_cols = {c["name"] for c in sa.inspect(bind).get_columns("tour_discounts")}
    if "funded_by" not in discount_cols:
        op.add_column(
            "tour_discounts",
            sa.Column("funded_by", sa.String(20), nullable=False, server_default="SUPPLIER"),
        )

    tier_cols = {c["name"] for c in sa.inspect(bind).get_columns("tour_group_discount_tiers")}
    if "funded_by" not in tier_cols:
        op.add_column(
            "tour_group_discount_tiers",
            sa.Column("funded_by", sa.String(20), nullable=False, server_default="SUPPLIER"),
        )


def downgrade():
    pass
