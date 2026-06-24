"""Add push_subscriptions table

Revision ID: 20260621_0016
Revises: 20260620_0015
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260621_0016"
down_revision = "20260620_0015"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _table_exists("push_subscriptions"):
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("endpoint", sa.String(500), nullable=False),
            sa.Column("p256dh", sa.String(256), nullable=False),
            sa.Column("auth", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("endpoint", name="uq_push_endpoint"),
        )


def downgrade():
    op.drop_table("push_subscriptions")
