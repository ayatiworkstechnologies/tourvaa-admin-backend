"""Per-item commissionable flag for optional activities/accommodation
extras/tour extensions, plus the booking-level non-commissionable-addon
snapshot.

Adds commissionable (default true) to tour_optional_activities,
tour_accommodation_extras and tour_extensions -- when false, that item's
price is excluded from Tourvaa's commission base but still paid to the
supplier in full. See services.bookings.compute_booking_supplier_financials
and services.bookings._price_booking.

Also adds Booking.non_commissionable_addon_amount, the per-booking snapshot
(at creation/edit time) of how much of optional_activity_amount /
accommodation_amount / extension_amount came from non-commissionable items.
Defaults to 0 so existing bookings (all addons commissionable) are unaffected.

Revision ID: 20260922_0116
Revises: 20260922_0115
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0116"
down_revision = "20260922_0115"
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
        if "commissionable" not in cols:
            op.add_column(
                table,
                sa.Column("commissionable", sa.Boolean(), nullable=False, server_default=sa.true()),
            )

    booking_cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    if "non_commissionable_addon_amount" not in booking_cols:
        op.add_column(
            "bookings",
            sa.Column("non_commissionable_addon_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        )


def downgrade():
    pass
