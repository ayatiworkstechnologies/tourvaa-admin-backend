"""Add the missing foreign key on customer_communications.booking_id.

Every other booking_id column in the schema is a proper FK to bookings.id;
this one was a bare, unconstrained integer, which allowed orphaned or
mistyped booking references. Any existing rows that don't point at a real
booking are nulled out first so the constraint can be added cleanly.

Revision ID: 20260917_0103
Revises: 20260916_0102
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260917_0103"
down_revision = "20260916_0102"
branch_labels = None
depends_on = None

TABLE = "customer_communications"
COLUMN = "booking_id"
FK_NAME = "fk_customer_communications_booking_id"


def _has_fk(inspector, table: str, fk_name: str) -> bool:
    return any(fk["name"] == fk_name for fk in inspector.get_foreign_keys(table))


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if _has_fk(inspector, TABLE, FK_NAME):
        return

    bind.execute(sa.text(
        f"UPDATE {TABLE} cc "
        f"LEFT JOIN bookings b ON b.id = cc.{COLUMN} "
        f"SET cc.{COLUMN} = NULL "
        f"WHERE cc.{COLUMN} IS NOT NULL AND b.id IS NULL"
    ))

    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.create_foreign_key(FK_NAME, "bookings", [COLUMN], ["id"])


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_fk(inspector, TABLE, FK_NAME):
        with op.batch_alter_table(TABLE) as batch_op:
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
