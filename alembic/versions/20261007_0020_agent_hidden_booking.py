"""Allow agents to dismiss unpaid gateway-return bookings from their own list.

Revision ID: 20261007_0020
Revises: 20261007_0019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261007_0020"
down_revision = "20261007_0019"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("bookings")}
    if "agent_hidden_at" not in columns:
        op.add_column("bookings", sa.Column("agent_hidden_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_bookings_agent_hidden_at", "bookings", ["agent_hidden_at"])


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("bookings")}
    if "agent_hidden_at" in columns:
        op.drop_index("ix_bookings_agent_hidden_at", table_name="bookings")
        op.drop_column("bookings", "agent_hidden_at")
