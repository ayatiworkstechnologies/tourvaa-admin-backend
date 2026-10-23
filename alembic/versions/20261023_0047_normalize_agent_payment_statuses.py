"""Normalize legacy agent reservation workflow values into payment outcomes.

Revision ID: 20261023_0047
Revises: 20261023_0046
"""

from alembic import op


revision = "20261023_0047"
down_revision = "20261023_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reservation method remains on agent_payment_method. These values were
    # workflow labels, not payment outcomes, and must not surface as payment
    # statuses in any portal.
    op.execute(
        "UPDATE bookings SET payment_status = 'pending' "
        "WHERE payment_status IN ('credit_approval_pending', 'bank_transfer_pending')"
    )
    op.execute(
        "UPDATE bookings SET booking_status = 'pending_payment' "
        "WHERE booking_status = 'pending_credit_approval'"
    )


def downgrade() -> None:
    # The original workflow label cannot be inferred safely from a normalized
    # pending payment, so this migration intentionally has no data reversal.
    pass
