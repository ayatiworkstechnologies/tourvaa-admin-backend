"""add booking_travellers.pickup_location / emergency_contact

Supports the Supplier Traveller Report - both columns start empty; there is
no UI yet to collect them, this migration only adds the storage.

Revision ID: 20260819_0074
Revises: 20260819_0073
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0074"
down_revision = "20260819_0073"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "booking_travellers", "pickup_location"):
        op.add_column("booking_travellers", sa.Column("pickup_location", sa.String(255), nullable=True))
    if not _has_column(inspector, "booking_travellers", "emergency_contact"):
        op.add_column("booking_travellers", sa.Column("emergency_contact", sa.String(150), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "booking_travellers", "emergency_contact"):
        op.drop_column("booking_travellers", "emergency_contact")
    if _has_column(inspector, "booking_travellers", "pickup_location"):
        op.drop_column("booking_travellers", "pickup_location")
