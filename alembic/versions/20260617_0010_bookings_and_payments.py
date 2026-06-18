"""Add bookings and payments tables

Revision ID: 20260617_0010
Revises: 20260616_0009
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260617_0010"
down_revision = "20260616_0009"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "bookings"):
        op.create_table(
            "bookings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("booking_code", sa.String(length=30), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("tour_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("agent_id", sa.Integer(), nullable=True),
            sa.Column("affiliate_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("cancelled_by", sa.Integer(), nullable=True),
            sa.Column("tour_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("tour_date", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("country", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("supplier_name", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("no_of_adults", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("no_of_children", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("no_of_infants", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_cost", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("amount_paid", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("amount_pending", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("booking_status", sa.String(length=30), nullable=False, server_default="upcoming"),
            sa.Column("payment_status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("cancellation_reason", sa.String(length=255), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["tour_id"], ["tours.id"]),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.ForeignKeyConstraint(["affiliate_id"], ["affiliates.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"]),
        )
        op.create_index("ix_bookings_id", "bookings", ["id"])
        op.create_index("ix_bookings_booking_code", "bookings", ["booking_code"], unique=True)
        op.create_index("ix_bookings_customer_id", "bookings", ["customer_id"])
        op.create_index("ix_bookings_tour_id", "bookings", ["tour_id"])
        op.create_index("ix_bookings_supplier_id", "bookings", ["supplier_id"])

    if not _has_table(inspector, "payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("payment_code", sa.String(length=30), nullable=True),
            sa.Column("booking_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("payment_method", sa.String(length=30), nullable=False, server_default="card"),
            sa.Column("payment_type", sa.String(length=30), nullable=False, server_default="advance"),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("pending_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("gst_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("refunded_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("payment_status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("transaction_id", sa.String(length=100), nullable=True),
            sa.Column("payment_date", sa.String(length=30), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("failure_reason", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        )
        op.create_index("ix_payments_id", "payments", ["id"])
        op.create_index("ix_payments_payment_code", "payments", ["payment_code"], unique=True)
        op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
        op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
        op.create_index("ix_payments_transaction_id", "payments", ["transaction_id"])


def downgrade():
    op.drop_table("payments")
    op.drop_table("bookings")
