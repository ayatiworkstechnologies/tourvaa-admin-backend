"""add user-scoped customer wishlist

Revision ID: 20260723_0027
Revises: 20260720_0026
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0027"
down_revision = "20260720_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_wishlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tour_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tour_id"], ["tours.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tour_id", name="uq_customer_wishlist_user_tour"),
    )
    op.create_index("ix_customer_wishlist_items_id", "customer_wishlist_items", ["id"], unique=False)
    op.create_index("ix_customer_wishlist_items_tour_id", "customer_wishlist_items", ["tour_id"], unique=False)
    op.create_index("ix_customer_wishlist_items_user_id", "customer_wishlist_items", ["user_id"], unique=False)


def downgrade():
    op.drop_index("ix_customer_wishlist_items_user_id", table_name="customer_wishlist_items")
    op.drop_index("ix_customer_wishlist_items_tour_id", table_name="customer_wishlist_items")
    op.drop_index("ix_customer_wishlist_items_id", table_name="customer_wishlist_items")
    op.drop_table("customer_wishlist_items")
