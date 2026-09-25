"""Restore Tourvaa's admin markup: booking snapshot columns.

The pricing slab already has admin_markup_value / storefront_*_price
(set to 0 / supplier price by 20260925_0001, so every existing tour keeps
its current customer price until an admin sets a markup). Bookings now
snapshot the markup so settlement pays the supplier on their own price:
  admin_markup_percentage  - markup % of the resolved slab
  supplier_base_amount     - traveller amount at supplier prices
  admin_markup_amount      - base_amount - supplier_base_amount
All nullable: existing bookings have no markup (split falls back to
base_amount), so their locked financials are unchanged.

Revision ID: 20260925_0002
Revises: 20260925_0001
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260925_0002"
down_revision = "20260925_0001"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("admin_markup_percentage", sa.Numeric(5, 2)),
    ("supplier_base_amount", sa.Numeric(12, 2)),
    ("admin_markup_amount", sa.Numeric(12, 2)),
)


def upgrade():
    existing = {c["name"] for c in inspect(op.get_bind()).get_columns("bookings")}
    for name, type_ in _COLUMNS:
        if name not in existing:
            op.add_column("bookings", sa.Column(name, type_, nullable=True))


def downgrade():
    existing = {c["name"] for c in inspect(op.get_bind()).get_columns("bookings")}
    for name, _type in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("bookings", name)
