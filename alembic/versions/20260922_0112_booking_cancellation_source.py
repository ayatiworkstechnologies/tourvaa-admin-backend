"""Track which side initiated a booking cancellation.

Adds bookings.cancellation_source ("customer_request", "admin", "supplier",
"system_expiry") so refund-percentage behavior (100% for admin/supplier/
system, RefundRule-tiered for customer_request) is auditable per booking
instead of only implied by which code path ran.

Revision ID: 20260922_0112
Revises: 20260922_0111
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0112"
down_revision = "20260922_0111"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("bookings")}
    if "cancellation_source" not in cols:
        op.add_column("bookings", sa.Column("cancellation_source", sa.String(30), nullable=True))


def downgrade():
    pass
