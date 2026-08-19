"""reconcile bookings/customers FKs and model-declared NOT NULL drift

`alembic check` reported ~217 differences between the SQLAlchemy models and
the live database. The large majority (~191) are cosmetic index-naming
differences - MySQL auto-creates an index for every FK/unique constraint
using its own naming convention, which doesn't match SQLAlchemy's
`ix_<table>_<column>` convention, so autogenerate sees them as "removed" +
"added" pairs even though the same index already exists under a different
name. Dropping and recreating ~170 indexes for a pure rename has real cost
(table locks, replication lag) and zero functional benefit, so this
migration deliberately does not touch them - see the audit action item
("reconcile deliberately; do not blindly autogenerate/drop indexes").

The two categories below are genuine drift with a real behavioral
difference, and both were verified safe against the live data before
writing this migration (0 orphaned FK rows, 0 NULLs in every affected
column):

1. Five foreign keys declared on the SQLAlchemy models were never actually
   created in the database (bookings.country_id/city_id/tour_calendar_id/
   booked_by_user_id, customers.blocked_by) - referential integrity for
   these columns was only enforced in application code, not by the DB.
2. Twenty-one columns are declared `nullable=False` on the model but the
   database still allows NULL.

Revision ID: 20260819_0072
Revises: 20260819_0071
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0072"
down_revision = "20260819_0071"
branch_labels = None
depends_on = None

_NOT_NULL_COLUMNS = [
    ("affiliate_marketing_info", "promotion_methods", sa.Text()),
    ("affiliate_marketing_info", "social_media_profiles", sa.Text()),
    ("affiliate_marketing_info", "existing_travel_platforms_used", sa.Text()),
    ("agent_business_info", "destinations_sold", sa.Text()),
    ("supplier_business_info", "destinations_sold", sa.Text()),
    ("supplier_vehicles", "vehicle_photos", sa.Text()),
    ("tour_accommodation_extras", "extra_price", sa.Numeric(12, 2)),
    ("tour_categories", "description", sa.Text()),
    ("tour_discounts", "discount_value", sa.Numeric(12, 2)),
    ("tour_discounts", "minimum_booking_amount", sa.Numeric(12, 2)),
    ("tour_extensions", "extra_price", sa.Numeric(12, 2)),
    ("tour_optional_activities", "price_per_person", sa.Numeric(12, 2)),
    ("tour_pricing", "adult_price", sa.Numeric(12, 2)),
    ("tour_pricing", "child_price", sa.Numeric(12, 2)),
    ("tour_pricing", "supplier_price", sa.Numeric(12, 2)),
    ("tour_pricing", "markup_value", sa.Numeric(12, 2)),
    ("tour_pricing", "final_price", sa.Numeric(12, 2)),
    ("tour_pricing", "admin_markup_value", sa.Numeric(12, 2)),
    ("tour_subcategories", "description", sa.Text()),
    ("tours", "short_description", sa.Text()),
    ("tours", "long_description", sa.Text()),
]

_FOREIGN_KEYS = [
    ("fk_bookings_country_id_countries", "bookings", "countries", "country_id", "id"),
    ("fk_bookings_city_id_cities", "bookings", "cities", "city_id", "id"),
    ("fk_bookings_tour_calendar_id_tour_calendar", "bookings", "tour_calendar", "tour_calendar_id", "id"),
    ("fk_bookings_booked_by_user_id_users", "bookings", "users", "booked_by_user_id", "id"),
    ("fk_customers_blocked_by_users", "customers", "users", "blocked_by", "id"),
]


def _existing_fk_names(inspector, table_name):
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, column_name, column_type in _NOT_NULL_COLUMNS:
        op.alter_column(table_name, column_name, existing_type=column_type, nullable=False)

    for fk_name, table_name, referent_table, local_col, remote_col in _FOREIGN_KEYS:
        if fk_name not in _existing_fk_names(inspector, table_name):
            op.create_foreign_key(fk_name, table_name, referent_table, [local_col], [remote_col])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for fk_name, table_name, _referent_table, _local_col, _remote_col in _FOREIGN_KEYS:
        if fk_name in _existing_fk_names(inspector, table_name):
            op.drop_constraint(fk_name, table_name, type_="foreignkey")

    for table_name, column_name, column_type in _NOT_NULL_COLUMNS:
        op.alter_column(table_name, column_name, existing_type=column_type, nullable=True)
