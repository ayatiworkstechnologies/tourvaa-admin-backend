"""add per-tour deposit configuration fields

Client requirement: supplier configures a minimum deposit percentage/amount and
how many days before departure a deposit is still allowed; past that cutoff the
customer must pay in full. This adds the columns; the balance-due-date formula
itself is intentionally not touched pending client confirmation.

Revision ID: 20260828_0087
Revises: 20260826_0086
"""

import sqlalchemy as sa
from alembic import op

revision = "20260828_0087"
down_revision = "20260826_0086"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tours", sa.Column("deposit_type", sa.String(20), nullable=False, server_default="fixed"))
    op.add_column("tours", sa.Column("deposit_percentage", sa.Float(), nullable=True))
    op.add_column("tours", sa.Column("deposit_cutoff_days", sa.Integer(), nullable=True))
    op.alter_column("tours", "deposit_type", server_default=None)


def downgrade():
    op.drop_column("tours", "deposit_cutoff_days")
    op.drop_column("tours", "deposit_percentage")
    op.drop_column("tours", "deposit_type")
