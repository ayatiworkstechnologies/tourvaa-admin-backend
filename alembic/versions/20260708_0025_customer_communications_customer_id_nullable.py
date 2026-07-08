"""Make customer_communications.customer_id nullable

Revision ID: 20260708_0025
Revises: 20260701_0024
Create Date: 2026-07-08

The supplier-portal and agent-portal support-message endpoints
(send_supplier_message / send_agent_message in app/routers/bookings.py)
insert a CustomerCommunication row with customer_id=None, since those
messages aren't tied to any customer. The SQLAlchemy model already
declares customer_id as nullable=True, but the original table-creation
migration (20260615_0007) mistakenly created the column NOT NULL, so
every supplier/agent support-message call has been failing with a
500 IntegrityError end-to-end.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260708_0025"
down_revision = "20260701_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "customer_communications",
        "customer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "customer_communications",
        "customer_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
