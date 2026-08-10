"""Invoice GST rate and balance due date.

Revision ID: 20260810_0058
Revises: 20260805_0057
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260810_0058"
down_revision = "20260805_0057"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "invoices", "gst_rate"):
        op.add_column(
            "invoices",
            sa.Column("gst_rate", sa.Numeric(5, 4), nullable=False, server_default="0.18"),
        )
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "invoices", "balance_due_date"):
        op.add_column(
            "invoices",
            sa.Column("balance_due_date", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "invoices", "balance_due_date"):
        op.drop_column("invoices", "balance_due_date")
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "invoices", "gst_rate"):
        op.drop_column("invoices", "gst_rate")
