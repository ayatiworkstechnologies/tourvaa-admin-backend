"""Monthly availability can run on several weeks of the month.

Adds tour_availability_configs.frequency_weeks (JSON list, 1-4 = 1st-4th
occurrence of a weekday, 5 = the last) and backfills existing monthly
schedules from their single frequency_week.

Revision ID: 20260922_0111
Revises: 20260921_0110
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0111"
down_revision = "20260921_0110"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("tour_availability_configs")}
    if "frequency_weeks" not in cols:
        op.add_column("tour_availability_configs", sa.Column("frequency_weeks", sa.JSON(), nullable=True))
    rows = bind.execute(sa.text(
        "SELECT id, frequency_week FROM tour_availability_configs WHERE frequency = 'monthly' AND frequency_week IS NOT NULL"
    )).fetchall()
    for row in rows:
        bind.execute(sa.text("UPDATE tour_availability_configs SET frequency_weeks = :w WHERE id = :i"), {"w": f"[{int(row[1])}]", "i": row[0]})


def downgrade():
    pass
