"""add supplier_commission_requests table

Supplier.commission_request_type/value/status/requested_at/reviewed_at were
scalar "current request only" columns -- a new request silently overwrote the
previous one with no history. This adds a history table (one row per
request), mirroring the existing supplier_approval_history pattern. The
scalar columns on suppliers are left as-is (still the fast "current state"
read) and continue to be written alongside the new history rows.

Revision ID: 20260728_0049
Revises: 20260728_0048
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0049"
down_revision = "20260728_0048"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "supplier_commission_requests"):
        op.create_table(
            "supplier_commission_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("markup_type", sa.String(length=20), nullable=False),
            sa.Column("markup_value", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_supplier_commission_requests_id"), "supplier_commission_requests", ["id"], unique=False)
        op.create_index(op.f("ix_supplier_commission_requests_supplier_id"), "supplier_commission_requests", ["supplier_id"], unique=False)
        op.create_index(op.f("ix_supplier_commission_requests_status"), "supplier_commission_requests", ["status"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "supplier_commission_requests"):
        op.drop_index(op.f("ix_supplier_commission_requests_status"), table_name="supplier_commission_requests")
        op.drop_index(op.f("ix_supplier_commission_requests_supplier_id"), table_name="supplier_commission_requests")
        op.drop_index(op.f("ix_supplier_commission_requests_id"), table_name="supplier_commission_requests")
        op.drop_table("supplier_commission_requests")
