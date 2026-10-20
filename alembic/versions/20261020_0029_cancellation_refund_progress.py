"""Persist cancellation-specific refund retry progress.

Revision ID: 20261020_0029
Revises: 20261015_0028
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0029"
down_revision = "20261015_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cancellation_requests",
        sa.Column("refund_processed_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("cancellation_requests", "refund_processed_amount")
