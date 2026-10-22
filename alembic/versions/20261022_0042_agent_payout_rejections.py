"""Persist agent payout rejection decisions.

Revision ID: 20261022_0042
Revises: 20261022_0041
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0042"
down_revision = "20261022_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_payouts", sa.Column("rejected_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("agent_payouts", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_payouts", sa.Column("rejection_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_payouts", "rejection_reason")
    op.drop_column("agent_payouts", "rejected_at")
    op.drop_column("agent_payouts", "rejected_by")
