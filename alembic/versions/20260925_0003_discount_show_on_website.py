"""Add tour_discounts.show_on_website.

Promo codes can now be listed on the tour page / checkout ("Available
offers") for one-click apply. Existing rows default to shown; admins untick
it for private codes (they keep working when typed). See
services.discounts.list_public_offers.

Revision ID: 20260925_0003
Revises: 20260925_0002
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260925_0003"
down_revision = "20260925_0002"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("tour_discounts")}
    if "show_on_website" not in columns:
        op.add_column("tour_discounts", sa.Column("show_on_website", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("tour_discounts")}
    if "show_on_website" in columns:
        op.drop_column("tour_discounts", "show_on_website")
