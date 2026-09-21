"""Add customers.customer_type and customers.agent_id.

Revision ID: 20260921_0110
Revises: 20260921_0109
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "20260921_0110"
down_revision = "20260921_0109"
branch_labels = None
depends_on = None


def upgrade():
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("customers")}
    if "customer_type" not in cols:
        op.add_column("customers", sa.Column("customer_type", sa.String(20), nullable=False, server_default="registered"))
        op.create_index("ix_customers_customer_type", "customers", ["customer_type"])
    if "agent_id" not in cols:
        op.add_column("customers", sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id"), nullable=True))
        op.create_index("ix_customers_agent_id", "customers", ["agent_id"])
    # Backfill: customers created by an agent, per the audit log
    op.execute(sa.text(
        "UPDATE customers c JOIN audit_logs a ON a.action = 'create_customer' AND a.entity_type = 'customer' AND a.entity_id = c.id "
        "JOIN agents g ON g.user_id = a.actor_user_id "
        "SET c.customer_type = 'agent', c.agent_id = g.id"
    ))


def downgrade():
    pass
