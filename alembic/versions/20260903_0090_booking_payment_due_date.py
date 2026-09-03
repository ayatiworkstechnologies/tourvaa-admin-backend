"""Supplier-set payment due date on bookings.

Revision ID: 20260903_0090
Revises: 20260902_0089
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260903_0090"
down_revision = "20260902_0089"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "bookings", "payment_due_date"):
        op.add_column(
            "bookings",
            sa.Column("payment_due_date", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "bookings", "payment_due_date"):
        op.drop_column("bookings", "payment_due_date")
