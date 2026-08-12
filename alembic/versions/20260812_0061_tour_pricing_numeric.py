"""Convert tour pricing Float columns to Numeric(12,2).

Revision ID: 20260812_0061
Revises: 20260810_0060
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa


revision = "20260812_0061"
down_revision = "20260810_0060"
branch_labels = None
depends_on = None


_NUMERIC = sa.Numeric(12, 2)
_FLOAT = sa.Float()

_COLUMNS = [
    ("tour_pricing", "adult_price"),
    ("tour_pricing", "child_price"),
    ("tour_pricing", "supplier_price"),
    ("tour_pricing", "markup_value"),
    ("tour_pricing", "final_price"),
    ("tour_pricing", "supplier_final_adult_price"),
    ("tour_pricing", "supplier_final_child_price"),
    ("tour_pricing", "admin_markup_value"),
    ("tour_pricing", "storefront_adult_price"),
    ("tour_pricing", "storefront_child_price"),
    ("tour_optional_activities", "price_per_person"),
    ("tour_accommodation_extras", "extra_price"),
    ("tour_extensions", "extra_price"),
    ("tour_discounts", "discount_value"),
    ("tour_discounts", "minimum_booking_amount"),
]


def upgrade():
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=_NUMERIC, existing_type=_FLOAT)


def downgrade():
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=_FLOAT, existing_type=_NUMERIC)
