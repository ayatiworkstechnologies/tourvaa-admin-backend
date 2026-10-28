"""Confirm legacy bookings already accepted by their supplier.

The supplier-accept flow now confirms a booking in the same transaction. Rows
created by the previous flow were left at ``supplier_accepted`` even though
their supplier decision was already final, causing the customer and agent
portals to continue showing "Booking Request Received".

Revision ID: 20261028_0053
Revises: 20261028_0052
"""

from alembic import op


revision = "20261028_0053"
down_revision = "20261028_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE bookings SET booking_status = 'confirmed' "
        "WHERE booking_status = 'supplier_accepted' "
        "AND supplier_acceptance_status = 'accepted'"
    )


def downgrade() -> None:
    # A confirmed booking may have progressed further after this migration;
    # restoring the stale intermediate state is neither safe nor useful.
    pass
