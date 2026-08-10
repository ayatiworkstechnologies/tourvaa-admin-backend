"""Two-factor authentication backup codes.

Revision ID: 20260810_0060
Revises: 20260810_0059
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260810_0060"
down_revision = "20260810_0059"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "users", "two_factor_backup_codes"):
        op.add_column(
            "users",
            sa.Column("two_factor_backup_codes", sa.Text(), nullable=True),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "users", "two_factor_backup_codes"):
        op.drop_column("users", "two_factor_backup_codes")
