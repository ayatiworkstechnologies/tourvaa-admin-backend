"""Remove optional-activities and accommodation-extras feature.

Revision ID: 20260903_0091
Revises: 20260903_0090
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260903_0091"
down_revision = "20260903_0090"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _has_column(inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())
    # Child tables (booking selections) first - they hold FKs into the tour
    # catalog tables dropped below.
    if _has_table(inspector, "booking_optional_activities"):
        op.drop_table("booking_optional_activities")
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "booking_accommodations"):
        op.drop_table("booking_accommodations")
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "tour_optional_activities"):
        op.drop_table("tour_optional_activities")
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "tour_accommodation_extras"):
        op.drop_table("tour_accommodation_extras")

    inspector = inspect(op.get_bind())
    if _has_column(inspector, "bookings", "optional_activity_amount"):
        op.drop_column("bookings", "optional_activity_amount")
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "bookings", "accommodation_amount"):
        op.drop_column("bookings", "accommodation_amount")


def downgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "bookings", "accommodation_amount"):
        op.add_column("bookings", sa.Column("accommodation_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "bookings", "optional_activity_amount"):
        op.add_column("bookings", sa.Column("optional_activity_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))

    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "tour_optional_activities"):
        op.create_table(
            "tour_optional_activities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("activity_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("price_per_person", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("image", sa.String(255), nullable=False, server_default=""),
            sa.Column("category", sa.String(30), nullable=False, server_default="other"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "tour_accommodation_extras"):
        op.create_table(
            "tour_accommodation_extras",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("accommodation_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("extra_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("price_type", sa.String(20), nullable=False, server_default="per_person"),
            sa.Column("image", sa.String(255), nullable=True),
            sa.Column("category", sa.String(30), nullable=False, server_default="room_upgrade"),
            sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "booking_optional_activities"):
        op.create_table(
            "booking_optional_activities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False, index=True),
            sa.Column("tour_optional_activity_id", sa.Integer(), sa.ForeignKey("tour_optional_activities.id"), nullable=True),
            sa.Column("activity_name_snapshot", sa.String(255), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "booking_accommodations"):
        op.create_table(
            "booking_accommodations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False, index=True),
            sa.Column("tour_accommodation_extra_id", sa.Integer(), sa.ForeignKey("tour_accommodation_extras.id"), nullable=True),
            sa.Column("accommodation_name_snapshot", sa.String(255), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("price_type", sa.String(30), nullable=False, server_default="per_person"),
            sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
