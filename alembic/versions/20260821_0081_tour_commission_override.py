"""add tours.commission_percentage (admin per-tour commission override)

Admin can now set Tourvaa's commission for a specific tour, overriding the
supplier's own rate / the platform minimum for bookings on that tour only.
Resolution order (see services.bookings.supplier_accept_booking): tour
override -> supplier's own commission_percentage -> platform minimum
(AppSetting "supplier_commission_percentage").

Revision ID: 20260821_0081
Revises: 20260821_0080
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0081"
down_revision = "20260821_0080"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "tours", "commission_percentage"):
        op.add_column("tours", sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "tours", "commission_percentage"):
        op.drop_column("tours", "commission_percentage")
