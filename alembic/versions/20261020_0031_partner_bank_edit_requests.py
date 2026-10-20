"""Add one-time partner bank-detail edit approval state.

Revision ID: 20261020_0031
Revises: 20261020_0030
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0031"
down_revision = "20261020_0030"
branch_labels = None
depends_on = None


TABLES = ("agent_invoicing", "supplier_invoicing", "affiliate_invoicing")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("bank_edit_requested_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("bank_edit_unlocked_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("bank_edit_unlocked_by", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_bank_edit_unlocked_by", table, "users", ["bank_edit_unlocked_by"], ["id"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f"fk_{table}_bank_edit_unlocked_by", table, type_="foreignkey")
        op.drop_column(table, "bank_edit_unlocked_by")
        op.drop_column(table, "bank_edit_unlocked_at")
        op.drop_column(table, "bank_edit_requested_at")
