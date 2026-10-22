"""Add persistent booking modification requests.

Revision ID: 20261022_0041
Revises: 20261022_0040
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0041"
down_revision = "20261022_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_modification_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requester_type", sa.String(length=30), nullable=False),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("original_values", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decision_history", sa.JSON(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_booking_modification_requests_booking_id", "booking_modification_requests", ["booking_id"])
    op.create_index("ix_booking_modification_requests_status", "booking_modification_requests", ["status"])
    op.create_index("ix_booking_modification_requests_requester_user_id", "booking_modification_requests", ["requester_user_id"])


def downgrade() -> None:
    op.drop_table("booking_modification_requests")
