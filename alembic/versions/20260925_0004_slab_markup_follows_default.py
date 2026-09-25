"""Pricing slabs can follow the platform default markup.

tour_pricing.admin_markup_value becomes nullable: NULL = no slab-specific
markup, use Settings' default_admin_markup_percentage (services/markup.py).
Every existing slab is 0 (reset by 20260925_0001, never set by an admin
since), so they're switched to NULL -- they then follow the default, which
is itself 0 today, so no price changes until an admin sets a default.

Revision ID: 20260925_0004
Revises: 20260925_0003
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = "20260925_0004"
down_revision = "20260925_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("tour_pricing", "admin_markup_value", existing_type=sa.Numeric(12, 2), nullable=True, server_default=None)
    op.execute("UPDATE tour_pricing SET admin_markup_value = NULL WHERE admin_markup_value = 0")


def downgrade():
    op.execute("UPDATE tour_pricing SET admin_markup_value = 0 WHERE admin_markup_value IS NULL")
    op.alter_column("tour_pricing", "admin_markup_value", existing_type=sa.Numeric(12, 2), nullable=False, server_default="0")
