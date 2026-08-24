"""add tour_pricing.commission_percentage

Per-slab supplier commission rate, floor-enforced against
resolve_effective_commission_percentage (Tour > Supplier > platform
minimum). Null means "use that resolved floor directly". See
services.tours._apply_pricing_computation.

Revision ID: 20260824_0083
Revises: 20260824_0082
"""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0083"
down_revision = "20260824_0082"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "tour_pricing", "commission_percentage"):
        op.add_column("tour_pricing", sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "tour_pricing", "commission_percentage"):
        op.drop_column("tour_pricing", "commission_percentage")
