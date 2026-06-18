"""Add user_id to affiliates table

Revision ID: 20260618_0012
Revises: 20260618_0011
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260618_0012"
down_revision = "20260618_0011"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())

    if "affiliates" in inspector.get_table_names():
        if not _has_column(inspector, "affiliates", "user_id"):
            op.add_column(
                "affiliates",
                sa.Column("user_id", sa.Integer(), nullable=True),
            )
            op.create_index("ix_affiliates_user_id", "affiliates", ["user_id"])
            op.create_foreign_key(
                "fk_affiliates_user_id_users",
                "affiliates",
                "users",
                ["user_id"],
                ["id"],
            )


def downgrade():
    inspector = inspect(op.get_bind())

    if "affiliates" in inspector.get_table_names():
        if _has_column(inspector, "affiliates", "user_id"):
            op.drop_constraint("fk_affiliates_user_id_users", "affiliates", type_="foreignkey")
            op.drop_index("ix_affiliates_user_id", table_name="affiliates")
            op.drop_column("affiliates", "user_id")
