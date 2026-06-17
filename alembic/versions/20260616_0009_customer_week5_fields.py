"""add customer week 5 fields

Revision ID: 20260616_0009
Revises: 20260616_0008
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260616_0009"
down_revision = "20260616_0008"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(inspector, table_name, column):
    if not _has_column(inspector, table_name, column.name):
        op.add_column(table_name, column)


def _create_index(name, table_name, columns):
    try:
        op.create_index(name, table_name, columns, unique=False)
    except Exception:
        pass


def _create_fk(name, source_table, referent_table, local_cols, remote_cols):
    try:
        op.create_foreign_key(name, source_table, referent_table, local_cols, remote_cols)
    except Exception:
        pass


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "customers"):
        return

    columns = [
        sa.Column("country_id", sa.Integer(), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("address_line_1", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("address_line_2", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("postal_code", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("total_bookings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_bookings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelled_bookings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upcoming_bookings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_amount_pending", sa.Numeric(12, 2), nullable=False, server_default="0"),
    ]

    for column in columns:
        _add_column_if_missing(inspector, "customers", column)

    _create_index(op.f("ix_customers_country_id"), "customers", ["country_id"])
    _create_index(op.f("ix_customers_city_id"), "customers", ["city_id"])

    if _has_table(inspector, "countries"):
        _create_fk("fk_customers_country_id_countries", "customers", "countries", ["country_id"], ["id"])
    if _has_table(inspector, "cities"):
        _create_fk("fk_customers_city_id_cities", "customers", "cities", ["city_id"], ["id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "customers"):
        return

    for name in ["fk_customers_city_id_cities", "fk_customers_country_id_countries"]:
        try:
            op.drop_constraint(name, "customers", type_="foreignkey")
        except Exception:
            pass

    for name in [op.f("ix_customers_city_id"), op.f("ix_customers_country_id")]:
        try:
            op.drop_index(name, table_name="customers")
        except Exception:
            pass

    for column_name in [
        "total_amount_pending",
        "total_amount_paid",
        "upcoming_bookings",
        "cancelled_bookings",
        "completed_bookings",
        "total_bookings",
        "postal_code",
        "address_line_2",
        "address_line_1",
        "city_id",
        "country_id",
    ]:
        if _has_column(inspector, "customers", column_name):
            op.drop_column("customers", column_name)
