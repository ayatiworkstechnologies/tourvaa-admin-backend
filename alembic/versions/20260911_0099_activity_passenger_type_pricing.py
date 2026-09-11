"""Pricing audit fix: allow optional activities to be priced per passenger
type (adult/child/infant), not just a single flat price_per_person applied
uniformly to every traveller.

Adds tour_optional_activities.child_price_per_person (nullable -- falls back
to price_per_person when unset), .infant_price_per_person (nullable --
falls back to free when unset, but only once pricing_mode opts in), and
.pricing_mode ("flat" | "per_passenger_type").

Revision ID: 20260911_0099
Revises: 20260911_0098
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260911_0099"
down_revision = "20260911_0098"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())
    table = "tour_optional_activities"

    if not _has_column(inspector, table, "child_price_per_person"):
        op.add_column(table, sa.Column("child_price_per_person", sa.Numeric(12, 2), nullable=True))
    if not _has_column(inspector, table, "infant_price_per_person"):
        op.add_column(table, sa.Column("infant_price_per_person", sa.Numeric(12, 2), nullable=True))
    if not _has_column(inspector, table, "pricing_mode"):
        op.add_column(table, sa.Column("pricing_mode", sa.String(20), nullable=False, server_default="flat"))


def downgrade():
    inspector = inspect(op.get_bind())
    table = "tour_optional_activities"

    if _has_column(inspector, table, "pricing_mode"):
        op.drop_column(table, "pricing_mode")
    if _has_column(inspector, table, "infant_price_per_person"):
        op.drop_column(table, "infant_price_per_person")
    if _has_column(inspector, table, "child_price_per_person"):
        op.drop_column(table, "child_price_per_person")
