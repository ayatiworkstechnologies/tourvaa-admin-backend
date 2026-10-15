"""Allow Agent reservations to store traveller details without a Customer account.

Revision ID: 20261015_0028
Revises: 20261013_0027
Create Date: 2026-10-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20261015_0028"
down_revision = "20261013_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agent-created reservations are owned by the Agent.  Their traveller
    # manifest is operational data, so no Customer account is required.
    op.alter_column("bookings", "customer_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("payments", "customer_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("invoices", "customer_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Existing rows cannot safely be backfilled with a fabricated Customer.
    # Keep the nullable schema on downgrade to preserve Agent booking records.
    pass
