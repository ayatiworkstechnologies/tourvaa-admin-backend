"""Backfill payment customer references from their bookings.

Revision ID: 20261023_0044
Revises: 20261022_0043
"""

from alembic import op


revision = "20261023_0044"
down_revision = "20261022_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agent bookings can legitimately have no customer. Only repair records
    # whose linked booking has one, so no relationship is guessed.
    op.execute(
        """
        UPDATE payments
        SET customer_id = (
            SELECT bookings.customer_id
            FROM bookings
            WHERE bookings.id = payments.booking_id
        )
        WHERE customer_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM bookings
              WHERE bookings.id = payments.booking_id
                AND bookings.customer_id IS NOT NULL
          )
        """
    )


def downgrade() -> None:
    # A repaired value cannot safely be distinguished from an original value.
    pass
