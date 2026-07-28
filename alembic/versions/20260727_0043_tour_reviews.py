"""create tour_reviews table for real customer reviews tied to completed bookings

The only "review" concept that existed before this was an admin-authored CMS
testimonial (cms_customer_reviews) with no link to a real Customer/Booking/Tour.
This adds a genuine customer-submitted, booking-scoped review with admin
moderation (pending/approved/rejected), feeding real ratings into the public
tour listing/detail pages.

Revision ID: 20260727_0043
Revises: 20260727_0042
"""

from alembic import op
import sqlalchemy as sa

revision = "20260727_0043"
down_revision = "20260727_0042"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tour_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("tour_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["tour_id"], ["tours.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_tour_reviews_booking"),
    )
    op.create_index("ix_tour_reviews_id", "tour_reviews", ["id"], unique=False)
    op.create_index("ix_tour_reviews_customer_id", "tour_reviews", ["customer_id"], unique=False)
    op.create_index("ix_tour_reviews_tour_id", "tour_reviews", ["tour_id"], unique=False)
    op.create_index("ix_tour_reviews_status", "tour_reviews", ["status"], unique=False)


def downgrade():
    # drop_table removes the table's indexes/FKs together - dropping them
    # individually first fails in MySQL since the FK constraints depend on them.
    op.drop_table("tour_reviews")
