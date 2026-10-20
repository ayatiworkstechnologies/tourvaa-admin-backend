"""Record the booking that redeemed each discount.

Revision ID: 20261020_0032
Revises: 20261020_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0032"
down_revision = "20261020_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tour_discount_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discount_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["discount_id"], ["tour_discounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discount_id", "booking_id", name="uq_tour_discount_redemption_booking"),
    )
    op.create_index("ix_tour_discount_redemptions_discount_id", "tour_discount_redemptions", ["discount_id"])
    op.create_index("ix_tour_discount_redemptions_booking_id", "tour_discount_redemptions", ["booking_id"])
    op.create_index("ix_tour_discount_redemptions_applied_at", "tour_discount_redemptions", ["applied_at"])


def downgrade() -> None:
    op.drop_index("ix_tour_discount_redemptions_applied_at", table_name="tour_discount_redemptions")
    op.drop_index("ix_tour_discount_redemptions_booking_id", table_name="tour_discount_redemptions")
    op.drop_index("ix_tour_discount_redemptions_discount_id", table_name="tour_discount_redemptions")
    op.drop_table("tour_discount_redemptions")
