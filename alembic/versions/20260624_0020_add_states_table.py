"""Add states table and state_id to cities

Revision ID: 20260624_0020
Revises: 20260623_0019
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260624_0020"
down_revision = "20260623_0019"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    cols = [c["name"] for c in inspect(op.get_bind()).get_columns(table)]
    return column in cols


def upgrade():
    if not _has_table("states"):
        op.create_table(
            "states",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("country_id", sa.Integer, sa.ForeignKey("countries.id"), nullable=False, index=True),
            sa.Column("state_name", sa.String(150), nullable=False),
            sa.Column("state_code", sa.String(10), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if _has_table("cities") and not _has_column("cities", "state_id"):
        op.add_column(
            "cities",
            sa.Column("state_id", sa.Integer, sa.ForeignKey("states.id"), nullable=True, index=True),
        )


def downgrade():
    if _has_table("cities") and _has_column("cities", "state_id"):
        op.drop_column("cities", "state_id")
    if _has_table("states"):
        op.drop_table("states")
