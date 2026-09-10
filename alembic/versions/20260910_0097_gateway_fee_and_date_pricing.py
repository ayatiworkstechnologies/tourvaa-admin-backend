"""Pricing audit fixes: add tours.gateway_fee_percentage (Stripe/PayPal
transaction fee, applied like tax_percentage so the displayed total matches
what the gateway actually captures) and tour_date_prices (per-date storefront
price overrides for seasonal/peak pricing).

Revision ID: 20260910_0097
Revises: 20260910_0096
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260910_0097"
down_revision = "20260910_0096"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_column(inspector, "tours", "gateway_fee_percentage"):
        op.add_column(
            "tours",
            sa.Column("gateway_fee_percentage", sa.Float(), nullable=False, server_default="0"),
        )

    if not _has_table(inspector, "tour_date_prices"):
        op.create_table(
            "tour_date_prices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("price_date", sa.Date(), nullable=False, index=True),
            sa.Column("adult_price", sa.Numeric(12, 2), nullable=False),
            sa.Column("child_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tour_id", "price_date", name="uq_tour_date_prices_tour_date"),
        )


def downgrade():
    inspector = inspect(op.get_bind())

    if _has_table(inspector, "tour_date_prices"):
        op.drop_table("tour_date_prices")

    if _has_column(inspector, "tours", "gateway_fee_percentage"):
        op.drop_column("tours", "gateway_fee_percentage")
