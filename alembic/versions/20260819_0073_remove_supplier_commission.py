"""remove supplier commission-request workflow

Suppliers no longer negotiate a commission rate. Tourvaa pays a supplier
the full tour price they set (no cut taken); the admin-only per-tour
markup (tour_pricing.admin_markup_value, now bounded 5-15%) is Tourvaa's
entire commission, added on top for the customer-facing price. This drops
the now-unused supplier-side commission-request history table and columns,
plus the mirrored "supplier's commission" columns on tour_pricing.

Revision ID: 20260819_0073
Revises: 20260819_0072
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0073"
down_revision = "20260819_0072"
branch_labels = None
depends_on = None

_SUPPLIER_COLUMNS = [
    ("markup_type", sa.String(20)),
    ("markup_value", sa.Float()),
    ("commission_request_type", sa.String(20)),
    ("commission_request_value", sa.Float()),
    ("commission_request_status", sa.String(20)),
    ("commission_requested_at", sa.DateTime(timezone=True)),
    ("commission_reviewed_at", sa.DateTime(timezone=True)),
]

_TOUR_PRICING_COLUMNS = [
    ("markup_type", sa.String(20)),
    ("markup_value", sa.Numeric(12, 2)),
]


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "supplier_commission_requests"):
        op.drop_table("supplier_commission_requests")

    for column_name, _column_type in _SUPPLIER_COLUMNS:
        if _has_column(inspector, "suppliers", column_name):
            op.drop_column("suppliers", column_name)

    for column_name, _column_type in _TOUR_PRICING_COLUMNS:
        if _has_column(inspector, "tour_pricing", column_name):
            op.drop_column("tour_pricing", column_name)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for column_name, column_type in _TOUR_PRICING_COLUMNS:
        if not _has_column(inspector, "tour_pricing", column_name):
            op.add_column("tour_pricing", sa.Column(column_name, column_type, nullable=True))

    for column_name, column_type in _SUPPLIER_COLUMNS:
        if not _has_column(inspector, "suppliers", column_name):
            op.add_column("suppliers", sa.Column(column_name, column_type, nullable=True))

    if not _has_table(inspector, "supplier_commission_requests"):
        op.create_table(
            "supplier_commission_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False, index=True),
            sa.Column("markup_type", sa.String(20), nullable=False),
            sa.Column("markup_value", sa.Float(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
