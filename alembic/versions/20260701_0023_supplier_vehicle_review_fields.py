"""Add review fields to supplier_vehicles

Revision ID: 20260701_0023
Revises: 20260701_0022
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260701_0023"
down_revision = "20260701_0022"
branch_labels = None
depends_on = None

TABLE = "supplier_vehicles"


def _has_column(column: str) -> bool:
    cols = [c["name"] for c in inspect(op.get_bind()).get_columns(TABLE)]
    return column in cols


def upgrade():
    if not _has_column("rejection_reason"):
        op.add_column(TABLE, sa.Column("rejection_reason", sa.String(255), nullable=True))
    if not _has_column("reviewed_at"):
        op.add_column(TABLE, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("reviewed_by"):
        op.add_column(TABLE, sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True))


def downgrade():
    if _has_column("reviewed_by"):
        op.drop_column(TABLE, "reviewed_by")
    if _has_column("reviewed_at"):
        op.drop_column(TABLE, "reviewed_at")
    if _has_column("rejection_reason"):
        op.drop_column(TABLE, "rejection_reason")
