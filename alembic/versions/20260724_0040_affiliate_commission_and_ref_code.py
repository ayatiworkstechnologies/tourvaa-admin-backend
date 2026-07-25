"""add affiliates.commission_percentage and bookings.affiliate_ref_code

record_conversion() (app/services/affiliate_tracking.py) already reads
Affiliate.commission_percentage to price a conversion, but no such column
ever existed on the model - every conversion would be commission_amount=0.
Also adds bookings.affiliate_ref_code so the referral code captured at
booking-creation time can be used later, at payment confirmation, to create
the AffiliateConversion (conversions should reflect real, paid outcomes -
not just attribution intent at booking creation).

Revision ID: 20260724_0040
Revises: 20260724_0039
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0040"
down_revision = "20260724_0039"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("affiliates", "commission_percentage"):
        op.add_column("affiliates", sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=False, server_default="0"))
    if not _has_column("bookings", "affiliate_ref_code"):
        op.add_column("bookings", sa.Column("affiliate_ref_code", sa.String(length=60), nullable=True))


def downgrade():
    if _has_column("bookings", "affiliate_ref_code"):
        op.drop_column("bookings", "affiliate_ref_code")
    if _has_column("affiliates", "commission_percentage"):
        op.drop_column("affiliates", "commission_percentage")
