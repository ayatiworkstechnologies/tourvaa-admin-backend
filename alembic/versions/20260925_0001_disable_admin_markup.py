"""Normalize pricing to the commission-only model.

Revision ID: 20260925_0001
Revises: 20260924_0002
Create Date: 2026-09-25
"""
from alembic import op


revision = "20260925_0001"
down_revision = "20260924_0002"
branch_labels = None
depends_on = None


def upgrade():
    # Customer-facing prices now equal supplier-listed prices. Keeping the
    # compatibility columns synchronized prevents exports and older clients
    # from observing stale markup-inclusive values.
    op.execute(
        """
        UPDATE tour_pricing
        SET admin_markup_type = 'percentage',
            admin_markup_value = 0,
            storefront_adult_price = adult_price,
            storefront_child_price = child_price,
            final_price = adult_price
        """
    )
    op.execute(
        """
        UPDATE tours AS t
        LEFT JOIN (
            SELECT tour_id, MIN(adult_price) AS minimum_price
            FROM tour_pricing
            WHERE status = 'active'
            GROUP BY tour_id
        ) AS p ON p.tour_id = t.id
        SET t.price_start_per_person = COALESCE(p.minimum_price, 0)
        """
    )


def downgrade():
    # Historical markup values cannot be reconstructed after normalization.
    # The schema remains compatible; restoring a pre-migration backup is the
    # safe rollback for the former pricing policy.
    pass
