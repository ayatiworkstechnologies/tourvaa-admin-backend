"""Add customer portal saved travellers and cancellations

Revision ID: 20260622_0018
Revises: 20260621_0017
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260622_0018"
down_revision = "20260621_0017"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade():
    if _has_table("customers"):
        if not _has_column("customers", "phone_country_code"):
            op.add_column("customers", sa.Column("phone_country_code", sa.String(length=10), nullable=False, server_default=""))
        if not _has_column("customers", "date_of_birth"):
            op.add_column("customers", sa.Column("date_of_birth", sa.DateTime(timezone=True), nullable=True))
        if not _has_column("customers", "gender"):
            op.add_column("customers", sa.Column("gender", sa.String(length=30), nullable=True))
        if not _has_column("customers", "email_verified"):
            op.add_column("customers", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        if not _has_column("customers", "phone_verified"):
            op.add_column("customers", sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()))

    if not _has_table("customer_saved_travellers"):
        op.create_table(
            "customer_saved_travellers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("traveller_name", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("phone", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("traveller_type", sa.String(length=20), nullable=False, server_default="adult"),
            sa.Column("age", sa.Integer(), nullable=True),
            sa.Column("gender", sa.String(length=30), nullable=True),
            sa.Column("passport_number", sa.String(length=100), nullable=True),
            sa.Column("allergies", sa.Text(), nullable=True),
            sa.Column("special_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_customer_saved_travellers_id"), "customer_saved_travellers", ["id"], unique=False)
        op.create_index(op.f("ix_customer_saved_travellers_customer_id"), "customer_saved_travellers", ["customer_id"], unique=False)

    if not _has_table("customer_cancellation_requests"):
        op.create_table(
            "customer_cancellation_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("booking_id", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="requested"),
            sa.Column("admin_notes", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_customer_cancellation_requests_id"), "customer_cancellation_requests", ["id"], unique=False)
        op.create_index(op.f("ix_customer_cancellation_requests_customer_id"), "customer_cancellation_requests", ["customer_id"], unique=False)
        op.create_index(op.f("ix_customer_cancellation_requests_booking_id"), "customer_cancellation_requests", ["booking_id"], unique=False)
        op.create_index(op.f("ix_customer_cancellation_requests_status"), "customer_cancellation_requests", ["status"], unique=False)


def downgrade():
    if _has_table("customer_cancellation_requests"):
        op.drop_index(op.f("ix_customer_cancellation_requests_status"), table_name="customer_cancellation_requests")
        op.drop_index(op.f("ix_customer_cancellation_requests_booking_id"), table_name="customer_cancellation_requests")
        op.drop_index(op.f("ix_customer_cancellation_requests_customer_id"), table_name="customer_cancellation_requests")
        op.drop_index(op.f("ix_customer_cancellation_requests_id"), table_name="customer_cancellation_requests")
        op.drop_table("customer_cancellation_requests")
    if _has_table("customer_saved_travellers"):
        op.drop_index(op.f("ix_customer_saved_travellers_customer_id"), table_name="customer_saved_travellers")
        op.drop_index(op.f("ix_customer_saved_travellers_id"), table_name="customer_saved_travellers")
        op.drop_table("customer_saved_travellers")
    if _has_column("customers", "phone_verified"):
        op.drop_column("customers", "phone_verified")
    if _has_column("customers", "email_verified"):
        op.drop_column("customers", "email_verified")
    if _has_column("customers", "gender"):
        op.drop_column("customers", "gender")
    if _has_column("customers", "date_of_birth"):
        op.drop_column("customers", "date_of_birth")
    if _has_column("customers", "phone_country_code"):
        op.drop_column("customers", "phone_country_code")
