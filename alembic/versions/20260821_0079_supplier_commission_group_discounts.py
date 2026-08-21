"""reintroduce supplier-visible commission and tour-level group discount tiers

The client has asked for the opposite of migration 20260819_0073: suppliers
should see a real commission percentage (admin sets a 10% platform minimum,
suppliers may raise it but not go below the minimum), plus supplier-defined
group-size discount tiers scoped to a whole Tour (not to an individual
tour_pricing slab) whose discount reduces the booking amount that commission
is then calculated against. This adds:

- suppliers.commission_percentage (nullable; null = use the platform
  minimum stored in the existing "supplier_commission_percentage"
  AppSetting row, see app/services/settings.py:get_commission_percentage).
- tour_group_discount_tiers, a new table of supplier-defined pax-range
  discounts keyed by tour_id.
- bookings.group_discount_tier_id / bookings.group_discount_amount, an
  audit trail of what group discount (if any) was applied to a booking.

Revision ID: 20260821_0079
Revises: 20260821_0078
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0079"
down_revision = "20260821_0078"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "suppliers", "commission_percentage"):
        op.add_column("suppliers", sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=True))

    if not _has_table(inspector, "tour_group_discount_tiers"):
        op.create_table(
            "tour_group_discount_tiers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("min_pax", sa.Integer(), nullable=False),
            sa.Column("max_pax", sa.Integer(), nullable=False),
            sa.Column("discount_type", sa.String(20), nullable=False),
            sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_column(inspector, "bookings", "group_discount_tier_id"):
        op.add_column(
            "bookings",
            sa.Column("group_discount_tier_id", sa.Integer(), sa.ForeignKey("tour_group_discount_tiers.id"), nullable=True),
        )
    if not _has_column(inspector, "bookings", "group_discount_amount"):
        op.add_column("bookings", sa.Column("group_discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "bookings", "group_discount_amount"):
        op.drop_column("bookings", "group_discount_amount")
    if _has_column(inspector, "bookings", "group_discount_tier_id"):
        op.drop_column("bookings", "group_discount_tier_id")

    if _has_table(inspector, "tour_group_discount_tiers"):
        op.drop_table("tour_group_discount_tiers")

    if _has_column(inspector, "suppliers", "commission_percentage"):
        op.drop_column("suppliers", "commission_percentage")
