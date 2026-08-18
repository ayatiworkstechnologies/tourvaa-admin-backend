"""add tour_availability_configs table

Client feedback ("Pricing & Tours Feedback" doc, pages 9-12): suppliers/admins
need to define a recurring availability schedule per tour - a Tour Start/End
Date range, a "Minimum Advance Booking (Days)" window, and a Weekly/
Fortnightly/Monthly frequency (with day-of-week / week-of-month selection) -
which services.tour_availability expands into concrete tour_calendar rows.

Revision ID: 20260818_0068
Revises: 20260818_0067
"""

import sqlalchemy as sa
from alembic import op

revision = "20260818_0068"
down_revision = "20260818_0067"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tour_availability_configs" in inspector.get_table_names():
        return

    op.create_table(
        "tour_availability_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, unique=True, index=True),
        sa.Column("availability_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("availability_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("min_advance_booking_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frequency", sa.String(20), nullable=True),
        sa.Column("frequency_week", sa.Integer(), nullable=True),
        sa.Column("frequency_days", sa.JSON(), nullable=True),
        sa.Column("seats_per_occurrence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_end_date_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tour_availability_configs" in inspector.get_table_names():
        op.drop_table("tour_availability_configs")
