"""add agent commission request fields

Revision ID: 20260723_0029
Revises: 20260723_0028
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0029"
down_revision = "20260723_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("commission_request_type", sa.String(length=20), nullable=True))
    op.add_column("agents", sa.Column("commission_request_value", sa.Float(), nullable=True))
    op.add_column("agents", sa.Column("commission_request_status", sa.String(length=20), nullable=True))
    op.add_column("agents", sa.Column("commission_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("commission_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agents_commission_request_status", "agents", ["commission_request_status"], unique=False)


def downgrade():
    op.drop_index("ix_agents_commission_request_status", table_name="agents")
    op.drop_column("agents", "commission_reviewed_at")
    op.drop_column("agents", "commission_requested_at")
    op.drop_column("agents", "commission_request_status")
    op.drop_column("agents", "commission_request_value")
    op.drop_column("agents", "commission_request_type")
