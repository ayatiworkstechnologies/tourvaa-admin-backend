"""supplier commission requests and payout paid_by audit trail

Revision ID: 20260724_0037
Revises: 20260724_0036
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0037"
down_revision = "20260724_0036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("suppliers", sa.Column("commission_request_type", sa.String(length=20), nullable=True))
    op.add_column("suppliers", sa.Column("commission_request_value", sa.Float(), nullable=True))
    op.add_column("suppliers", sa.Column("commission_request_status", sa.String(length=20), nullable=True))
    op.add_column("suppliers", sa.Column("commission_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("suppliers", sa.Column("commission_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_suppliers_commission_request_status", "suppliers", ["commission_request_status"], unique=False)

    op.add_column("supplier_payouts", sa.Column("paid_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_supplier_payouts_paid_by_users",
        "supplier_payouts",
        "users",
        ["paid_by"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_supplier_payouts_paid_by_users", "supplier_payouts", type_="foreignkey")
    op.drop_column("supplier_payouts", "paid_by")

    op.drop_index("ix_suppliers_commission_request_status", table_name="suppliers")
    op.drop_column("suppliers", "commission_reviewed_at")
    op.drop_column("suppliers", "commission_requested_at")
    op.drop_column("suppliers", "commission_request_status")
    op.drop_column("suppliers", "commission_request_value")
    op.drop_column("suppliers", "commission_request_type")
