"""Categorize contact enquiries by audience.

Revision ID: 20261009_0023
Revises: 20261008_0022
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261009_0023"
down_revision = "20261008_0022"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("contact_messages")}
    if "audience" not in columns:
        op.add_column("contact_messages", sa.Column("audience", sa.String(length=20), nullable=False, server_default="public"))
        op.create_index("ix_contact_messages_audience", "contact_messages", ["audience"])


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("contact_messages")}
    if "audience" in columns:
        op.drop_index("ix_contact_messages_audience", table_name="contact_messages")
        op.drop_column("contact_messages", "audience")
