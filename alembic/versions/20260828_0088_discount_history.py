"""add tour_discount_history append-only version log

Client requirement: Edit and Delete are removed from discount management;
suppliers/admins may only extend validity or change the percentage, and
every such change must create a new history/version record instead of
silently overwriting the original.

Revision ID: 20260828_0088
Revises: 20260828_0087
"""

import sqlalchemy as sa
from alembic import op

revision = "20260828_0088"
down_revision = "20260828_0087"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tour_discount_history",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("discount_id", sa.Integer(), sa.ForeignKey("tour_discounts.id"), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("discount_name", sa.String(255), nullable=False),
        sa.Column("discount_type", sa.String(20), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("tour_discount_history")
