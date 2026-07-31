"""add agent_ledgers, agent_payouts, agent_payout_items tables

Agent commission was previously only a live-recomputed dashboard estimate
(dashboard.py's commission_earned) - not a durable, payable record.
Mirrors the existing supplier_ledgers/supplier_payouts/supplier_payout_items
pattern, adapted for agent commission instead of supplier markup.

Revision ID: 20260730_0053
Revises: 20260730_0052
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0053"
down_revision = "20260730_0052"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "agent_ledgers"):
        op.create_table(
            "agent_ledgers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("booking_id", sa.Integer(), nullable=False),
            sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("commission_percentage", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("net_payable", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("amount_pending", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_agent_ledgers_id"), "agent_ledgers", ["id"], unique=False)
        op.create_index(op.f("ix_agent_ledgers_agent_id"), "agent_ledgers", ["agent_id"], unique=False)
        op.create_index(op.f("ix_agent_ledgers_booking_id"), "agent_ledgers", ["booking_id"], unique=False)
        op.create_index(op.f("ix_agent_ledgers_status"), "agent_ledgers", ["status"], unique=False)

    if not _has_table(inspector, "agent_payouts"):
        op.create_table(
            "agent_payouts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("payout_code", sa.String(length=30), nullable=True),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
            sa.Column("payment_method", sa.String(length=50), nullable=False, server_default="bank_transfer"),
            sa.Column("reference_number", sa.String(length=150), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("initiated_by", sa.Integer(), nullable=True),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("paid_by", sa.Integer(), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.ForeignKeyConstraint(["initiated_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["paid_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_agent_payouts_id"), "agent_payouts", ["id"], unique=False)
        op.create_index(op.f("ix_agent_payouts_payout_code"), "agent_payouts", ["payout_code"], unique=True)
        op.create_index(op.f("ix_agent_payouts_agent_id"), "agent_payouts", ["agent_id"], unique=False)
        op.create_index(op.f("ix_agent_payouts_status"), "agent_payouts", ["status"], unique=False)

    if not _has_table(inspector, "agent_payout_items"):
        op.create_table(
            "agent_payout_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("payout_id", sa.Integer(), nullable=False),
            sa.Column("ledger_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["payout_id"], ["agent_payouts.id"]),
            sa.ForeignKeyConstraint(["ledger_id"], ["agent_ledgers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_agent_payout_items_id"), "agent_payout_items", ["id"], unique=False)
        op.create_index(op.f("ix_agent_payout_items_payout_id"), "agent_payout_items", ["payout_id"], unique=False)
        op.create_index(op.f("ix_agent_payout_items_ledger_id"), "agent_payout_items", ["ledger_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "agent_payout_items"):
        op.drop_index(op.f("ix_agent_payout_items_ledger_id"), table_name="agent_payout_items")
        op.drop_index(op.f("ix_agent_payout_items_payout_id"), table_name="agent_payout_items")
        op.drop_index(op.f("ix_agent_payout_items_id"), table_name="agent_payout_items")
        op.drop_table("agent_payout_items")

    if _has_table(inspector, "agent_payouts"):
        op.drop_index(op.f("ix_agent_payouts_status"), table_name="agent_payouts")
        op.drop_index(op.f("ix_agent_payouts_agent_id"), table_name="agent_payouts")
        op.drop_index(op.f("ix_agent_payouts_payout_code"), table_name="agent_payouts")
        op.drop_index(op.f("ix_agent_payouts_id"), table_name="agent_payouts")
        op.drop_table("agent_payouts")

    if _has_table(inspector, "agent_ledgers"):
        op.drop_index(op.f("ix_agent_ledgers_status"), table_name="agent_ledgers")
        op.drop_index(op.f("ix_agent_ledgers_booking_id"), table_name="agent_ledgers")
        op.drop_index(op.f("ix_agent_ledgers_agent_id"), table_name="agent_ledgers")
        op.drop_index(op.f("ix_agent_ledgers_id"), table_name="agent_ledgers")
        op.drop_table("agent_ledgers")
