"""backfill supplier_vehicles.vehicle_type / registration_number

The SQLAlchemy model (app/models/suppliers.py) has declared
vehicle_type/registration_number on SupplierVehicle since early on, but no
prior migration ever added them -- the table-creation migration
(20260616_0008) predates those two columns. Environments whose schema was
bootstrapped some other way (e.g. Base.metadata.create_all()) already have
them; environments built purely through `alembic upgrade head` do not. This
migration closes that drift for the latter.

Revision ID: 20260724_0038
Revises: 20260724_0037
"""

import sqlalchemy as sa
from alembic import op

revision = "20260724_0038"
down_revision = "20260724_0037"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("supplier_vehicles", "vehicle_type"):
        op.add_column("supplier_vehicles", sa.Column("vehicle_type", sa.String(length=75), nullable=False, server_default=""))
    if not _has_column("supplier_vehicles", "registration_number"):
        op.add_column("supplier_vehicles", sa.Column("registration_number", sa.String(length=100), nullable=False, server_default=""))


def downgrade():
    if _has_column("supplier_vehicles", "registration_number"):
        op.drop_column("supplier_vehicles", "registration_number")
    if _has_column("supplier_vehicles", "vehicle_type"):
        op.drop_column("supplier_vehicles", "vehicle_type")
