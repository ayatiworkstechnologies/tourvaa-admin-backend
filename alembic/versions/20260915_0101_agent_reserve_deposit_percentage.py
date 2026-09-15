"""Add tour_availability_configs.agent_reserve_deposit_percentage - agent
"Reserve Now" bookings (pay_later) used to require $0 upfront; the client
now wants a reduced deposit (default 30%) charged immediately instead, with
the remaining balance still due per the existing agent no-deposit buffer
window. See services.tour_availability.agent_reserve_eligibility/
agent_reserve_deposit_amount.

Revision ID: 20260915_0101
Revises: 20260911_0100
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260915_0101"
down_revision = "20260911_0100"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_column(inspector, "tour_availability_configs", "agent_reserve_deposit_percentage"):
        op.add_column(
            "tour_availability_configs",
            sa.Column("agent_reserve_deposit_percentage", sa.Float(), nullable=False, server_default="30"),
        )


def downgrade():
    inspector = inspect(op.get_bind())

    if _has_column(inspector, "tour_availability_configs", "agent_reserve_deposit_percentage"):
        op.drop_column("tour_availability_configs", "agent_reserve_deposit_percentage")
