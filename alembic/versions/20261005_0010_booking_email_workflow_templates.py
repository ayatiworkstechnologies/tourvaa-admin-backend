"""Correct customer booking confirmation copy and add supplier confirmation template.

Revision ID: 20261005_0010
Revises: 20261005_0009
"""

from alembic import op


revision = "20261005_0010"
down_revision = "20261005_0009"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve any administrator customisation apart from the inaccurate
    # supplier-acceptance phrase this release corrects.
    op.execute(
        "UPDATE email_templates "
        "SET body = REPLACE(body, 'Great news! Your Tourvaa booking has been confirmed by the supplier.', 'Great news! Your Tourvaa booking is now confirmed.') "
        "WHERE `key` = 'booking_confirmed'"
    )


def downgrade():
    op.execute(
        "UPDATE email_templates "
        "SET body = REPLACE(body, 'Great news! Your Tourvaa booking is now confirmed.', 'Great news! Your Tourvaa booking has been confirmed by the supplier.') "
        "WHERE `key` = 'booking_confirmed'"
    )
