"""add pricing/currency snapshot columns to bookings

A booking only ever stored a flat `currency` column -- nothing tied it back
to which TourPricing slab, supplier price/currency, or exchange rate was
actually used to charge it. If pricing or commission changes later, there
was no way to reconstruct what a past booking was actually charged and why.
This adds a snapshot captured once at booking creation and never touched
again.

Revision ID: 20260804_0056
Revises: 20260804_0055
"""

import sqlalchemy as sa
from alembic import op

revision = "20260804_0056"
down_revision = "20260804_0055"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [
        ("pricing_slab_id", sa.Column("pricing_slab_id", sa.Integer(), sa.ForeignKey("tour_pricing.id"), nullable=True)),
        ("supplier_price", sa.Column("supplier_price", sa.Numeric(12, 2), nullable=True)),
        ("supplier_currency", sa.Column("supplier_currency", sa.String(10), nullable=True)),
        ("tourvaa_selling_price", sa.Column("tourvaa_selling_price", sa.Numeric(12, 2), nullable=True)),
        ("display_currency", sa.Column("display_currency", sa.String(10), nullable=True)),
        ("exchange_rate", sa.Column("exchange_rate", sa.Numeric(14, 6), nullable=True)),
        ("exchange_rate_source", sa.Column("exchange_rate_source", sa.String(30), nullable=True)),
        ("exchange_rate_captured_at", sa.Column("exchange_rate_captured_at", sa.DateTime(timezone=True), nullable=True)),
        ("converted_customer_amount", sa.Column("converted_customer_amount", sa.Numeric(12, 2), nullable=True)),
    ]
    for name, column in columns:
        if not _has_column(inspector, "bookings", name):
            op.add_column("bookings", column)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for name in [
        "converted_customer_amount", "exchange_rate_captured_at", "exchange_rate_source",
        "exchange_rate", "display_currency", "tourvaa_selling_price", "supplier_currency",
        "supplier_price", "pricing_slab_id",
    ]:
        if _has_column(inspector, "bookings", name):
            op.drop_column("bookings", name)
