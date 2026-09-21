"""Make all generated codes plain ids (1, 2, 3) instead of zero-padded/prefixed.

Revision ID: 20260921_0109
Revises: 20260919_0108
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa


revision = "20260921_0109"
down_revision = "20260919_0108"
branch_labels = None
depends_on = None

# (table, code column)
TARGETS = [
    ("tours", "tour_code"),
    ("agents", "agent_code"),
    ("affiliates", "affiliate_code"),
    ("customers", "customer_code"),
    ("bookings", "booking_code"),
    ("payments", "payment_code"),
    ("invoices", "invoice_number"),
    ("agent_payouts", "payout_code"),
    ("supplier_payouts", "payout_code"),
    ("affiliate_payouts", "payout_code"),
]


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    for table, col in TARGETS:
        if table not in tables or col not in {c["name"] for c in insp.get_columns(table)}:
            continue
        if table == "bookings":
            bind.execute(sa.text(
                "UPDATE bookings SET booking_code = CONCAT(IF(booking_source = 'agent', 'TVAA-', 'TVAC-'), id) "
                "WHERE booking_code IS NOT NULL"
            ))
            continue
        bind.execute(sa.text(f"UPDATE {table} SET {col} = CAST(id AS CHAR) WHERE {col} IS NOT NULL"))


def downgrade():
    pass
