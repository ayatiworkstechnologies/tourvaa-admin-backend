"""Add delivery and read state to portal and booking chat messages.

Revision ID: 20261013_0027
Revises: 20261013_0026
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261013_0027"
down_revision = "20261013_0026"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    for table_name in ("messages", "booking_messages"):
        columns = _columns(table_name)
        if "delivered_at" not in columns:
            op.add_column(table_name, sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
        if "read_at" not in columns:
            op.add_column(table_name, sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table_name in ("booking_messages", "messages"):
        columns = _columns(table_name)
        if "read_at" in columns:
            op.drop_column(table_name, "read_at")
        if "delivered_at" in columns:
            op.drop_column(table_name, "delivered_at")
