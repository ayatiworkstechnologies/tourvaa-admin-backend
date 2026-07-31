"""add last_run_at to report_schedules

Report scheduling now has a real executor (a background loop in
app/main.py, see app/services/reports.py:run_due_report_schedules) that
needs to know when a schedule last fired to decide whether it's due.

Revision ID: 20260730_0052
Revises: 20260730_0051
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0052"
down_revision = "20260730_0051"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "report_schedules", "last_run_at"):
        op.add_column("report_schedules", sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "report_schedules", "last_run_at"):
        op.drop_column("report_schedules", "last_run_at")
