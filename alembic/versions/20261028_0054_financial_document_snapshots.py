"""Freeze booking policy and financial-document snapshots.

Revision ID: 20261028_0054
Revises: 20261028_0053
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_0054"
down_revision = "20261028_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("cancellation_policy_snapshot", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("recipient_type", sa.String(length=20), nullable=False, server_default="customer"))
    op.add_column("invoices", sa.Column("document_snapshot", sa.JSON(), nullable=True))
    op.alter_column("invoices", "recipient_type", server_default=None)


def downgrade() -> None:
    op.drop_column("invoices", "document_snapshot")
    op.drop_column("invoices", "recipient_type")
    op.drop_column("bookings", "cancellation_policy_snapshot")
