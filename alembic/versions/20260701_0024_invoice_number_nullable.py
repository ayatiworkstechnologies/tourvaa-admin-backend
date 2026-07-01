"""Make invoices.invoice_number nullable so it can be assigned after insert

Revision ID: 20260701_0024
Revises: 20260701_0023
Create Date: 2026-07-01

The invoice-generation flow inserts a row first (to get its auto-increment id),
then computes invoice_number from that id and updates the row — the same
pattern already used for customer_code/supplier_code/tour_code elsewhere,
all of which are nullable. invoice_number was mistakenly created NOT NULL,
so the initial insert failed and invoice auto-generation was broken end-to-end.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260701_0024"
down_revision = "20260701_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "invoices",
        "invoice_number",
        existing_type=sa.String(40),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "invoices",
        "invoice_number",
        existing_type=sa.String(40),
        nullable=False,
    )
