"""Add tours.admin_markup_percentage (per-tour Tourvaa markup).

Null = the tour uses the platform default markup. Resolution order for a
pricing slab: slab markup > tour markup > default (services/markup.py).
Nullable with no default, so no existing price changes.

Revision ID: 20260925_0005
Revises: 20260925_0004
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260925_0005"
down_revision = "20260925_0004"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("tours")}
    if "admin_markup_percentage" not in columns:
        op.add_column("tours", sa.Column("admin_markup_percentage", sa.Numeric(5, 2), nullable=True))


def downgrade():
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("tours")}
    if "admin_markup_percentage" in columns:
        op.drop_column("tours", "admin_markup_percentage")
