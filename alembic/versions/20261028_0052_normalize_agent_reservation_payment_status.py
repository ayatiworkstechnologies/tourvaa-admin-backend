"""Normalize legacy agent-reservation payment status values.

Credit approval and bank-transfer review are workflow details held in
``agent_payment_method``; they are not payment statuses.  Keeping them in
``bookings.payment_status`` made portal rows disagree with the payment-status
filters and exposed internal wording to agents and suppliers.

Revision ID: 20261028_0052
Revises: 20261024_0051
"""

from alembic import op


revision = "20261028_0052"
down_revision = "20261024_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE bookings SET payment_status = 'pending' "
        "WHERE payment_status IN ('credit_approval_pending', 'bank_transfer_pending')"
    )


def downgrade() -> None:
    # The former values cannot be reconstructed safely from a generic pending
    # row, and restoring them would reintroduce invalid public statuses.
    pass
