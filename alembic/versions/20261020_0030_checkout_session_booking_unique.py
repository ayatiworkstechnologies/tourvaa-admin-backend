"""Ensure a booking can be linked to only one checkout session.

Revision ID: 20261020_0030
Revises: 20261020_0029
"""

from alembic import op


revision = "20261020_0030"
down_revision = "20261020_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_checkout_sessions_booking_id", "checkout_sessions", ["booking_id"])


def downgrade() -> None:
    op.drop_constraint("uq_checkout_sessions_booking_id", "checkout_sessions", type_="unique")
