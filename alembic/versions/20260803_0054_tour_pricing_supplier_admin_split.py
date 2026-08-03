"""split tour_pricing into supplier price + admin markup + storefront price

The "Passenger Pricing" slab table let anyone type any final_price with no
link to the actual markup fields, and adult_price/child_price (the values
bookings.py actually charges) had no separation between what the supplier
is paid and what Tourvaa adds on top for fees/maintenance. This adds:
  - supplier_final_adult_price / supplier_final_child_price: adult/child
    price with the supplier's fixed commission applied (server-computed).
  - admin_markup_type / admin_markup_value: Tourvaa's own markup, set by
    admins only, applied on top of the supplier-final price.
  - storefront_adult_price / storefront_child_price: the true customer-
    facing price, server-computed, which bookings.py now charges from.

Existing rows are backfilled 1:1 (no markup) so behaviour is unchanged
until a slab is next saved through the new create/update logic.

Revision ID: 20260803_0054
Revises: 20260730_0053
"""

import sqlalchemy as sa
from alembic import op

revision = "20260803_0054"
down_revision = "20260730_0053"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "tour_pricing", "supplier_final_adult_price"):
        op.add_column("tour_pricing", sa.Column("supplier_final_adult_price", sa.Float(), nullable=True))
    if not _has_column(inspector, "tour_pricing", "supplier_final_child_price"):
        op.add_column("tour_pricing", sa.Column("supplier_final_child_price", sa.Float(), nullable=True))
    if not _has_column(inspector, "tour_pricing", "admin_markup_type"):
        op.add_column("tour_pricing", sa.Column("admin_markup_type", sa.String(20), nullable=False, server_default="percentage"))
    if not _has_column(inspector, "tour_pricing", "admin_markup_value"):
        op.add_column("tour_pricing", sa.Column("admin_markup_value", sa.Float(), nullable=False, server_default="0"))
    if not _has_column(inspector, "tour_pricing", "storefront_adult_price"):
        op.add_column("tour_pricing", sa.Column("storefront_adult_price", sa.Float(), nullable=True))
    if not _has_column(inspector, "tour_pricing", "storefront_child_price"):
        op.add_column("tour_pricing", sa.Column("storefront_child_price", sa.Float(), nullable=True))

    op.execute(
        """
        UPDATE tour_pricing
        SET supplier_final_adult_price = adult_price,
            supplier_final_child_price = child_price,
            storefront_adult_price = adult_price,
            storefront_child_price = child_price
        WHERE storefront_adult_price IS NULL
        """
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for column in [
        "storefront_child_price",
        "storefront_adult_price",
        "admin_markup_value",
        "admin_markup_type",
        "supplier_final_child_price",
        "supplier_final_adult_price",
    ]:
        if _has_column(inspector, "tour_pricing", column):
            op.drop_column("tour_pricing", column)
