"""Store the booking party addressed by an Admin message.

Revision ID: 20261007_0021
Revises: 20261007_0020
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261007_0021"
down_revision = "20261007_0020"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("booking_messages")}
    if "recipient_role" not in columns:
        op.add_column("booking_messages", sa.Column("recipient_role", sa.String(length=20), nullable=True))


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("booking_messages")}
    if "recipient_role" in columns:
        op.drop_column("booking_messages", "recipient_role")
