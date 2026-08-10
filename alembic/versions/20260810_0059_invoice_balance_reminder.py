"""Invoice balance-due reminder tracking.

Revision ID: 20260810_0059
Revises: 20260810_0058
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260810_0059"
down_revision = "20260810_0058"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "invoices", "balance_reminder_stage"):
        op.add_column(
            "invoices",
            sa.Column("balance_reminder_stage", sa.String(20), nullable=True),
        )
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "invoices", "last_balance_reminder_at"):
        op.add_column(
            "invoices",
            sa.Column("last_balance_reminder_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "invoices", "last_balance_reminder_at"):
        op.drop_column("invoices", "last_balance_reminder_at")
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "invoices", "balance_reminder_stage"):
        op.drop_column("invoices", "balance_reminder_stage")
