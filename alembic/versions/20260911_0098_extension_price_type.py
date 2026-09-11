"""Pricing audit fix: add tour_extensions.price_type and extend accommodation/
extension price types to support per_room, per_person_per_night, and
per_room_per_night multipliers (accommodation/extension "nights" pricing gap
from the pricing audit -- previously only per_person or flat quantity).

Revision ID: 20260911_0098
Revises: 20260910_0097
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260911_0098"
down_revision = "20260910_0097"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_column(inspector, "tour_extensions", "price_type"):
        op.add_column(
            "tour_extensions",
            sa.Column("price_type", sa.String(20), nullable=False, server_default="per_booking"),
        )


def downgrade():
    inspector = inspect(op.get_bind())

    if _has_column(inspector, "tour_extensions", "price_type"):
        op.drop_column("tour_extensions", "price_type")
