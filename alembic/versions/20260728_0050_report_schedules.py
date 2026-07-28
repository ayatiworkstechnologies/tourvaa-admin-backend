"""add report_schedules table

Config-only shell for report scheduling: admins can save a delivery config
(report type, cadence, recipients) but nothing executes it yet -- that
requires picking a scheduler dependency, a separate follow-up decision.

Revision ID: 20260728_0050
Revises: 20260728_0049
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0050"
down_revision = "20260728_0049"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "report_schedules"):
        op.create_table(
            "report_schedules",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("report_type", sa.String(length=50), nullable=False),
            sa.Column("cadence", sa.String(length=20), nullable=False, server_default="weekly"),
            sa.Column("recipient_emails", sa.String(length=1000), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_report_schedules_id"), "report_schedules", ["id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "report_schedules"):
        op.drop_index(op.f("ix_report_schedules_id"), table_name="report_schedules")
        op.drop_table("report_schedules")
