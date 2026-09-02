"""add agent no-deposit buffer weeks to tour availability config

Client requirement: an agent booking more than this many weeks before the
tour's Minimum Advance Booking cutoff date may Reserve Now with no deposit,
with the balance due this many weeks before the travel date. Closer than
that, agents only see Pay in Full Today.

Revision ID: 20260902_0089
Revises: 20260828_0088
"""

import sqlalchemy as sa
from alembic import op

revision = "20260902_0089"
down_revision = "20260828_0088"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tour_availability_configs",
        sa.Column("agent_no_deposit_buffer_weeks", sa.Integer(), nullable=False, server_default="4"),
    )
    op.alter_column("tour_availability_configs", "agent_no_deposit_buffer_weeks", server_default=None)


def downgrade():
    op.drop_column("tour_availability_configs", "agent_no_deposit_buffer_weeks")
