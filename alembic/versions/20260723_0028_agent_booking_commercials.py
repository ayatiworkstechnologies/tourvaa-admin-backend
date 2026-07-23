"""add agent booking commercial fields

Revision ID: 20260723_0028
Revises: 20260723_0027
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0028"
down_revision = "20260723_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bookings", sa.Column("agent_net_price", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("bookings", sa.Column("agent_markup", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("bookings", sa.Column("customer_selling_price", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("bookings", sa.Column("agent_payment_method", sa.String(length=30), nullable=True))
    op.add_column("bookings", sa.Column("agent_reference", sa.String(length=100), nullable=True))
    op.execute("UPDATE bookings SET customer_selling_price = final_amount")


def downgrade():
    op.drop_column("bookings", "agent_reference")
    op.drop_column("bookings", "agent_payment_method")
    op.drop_column("bookings", "customer_selling_price")
    op.drop_column("bookings", "agent_markup")
    op.drop_column("bookings", "agent_net_price")
