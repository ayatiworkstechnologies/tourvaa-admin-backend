"""messages/booking_messages -> add soft-delete columns

Revision ID: 20260821_0077
Revises: 20260819_0076
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0077"
down_revision = "20260819_0076"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("messages", "booking_messages"):
        op.add_column(table, sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for table in ("messages", "booking_messages"):
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "is_deleted")
