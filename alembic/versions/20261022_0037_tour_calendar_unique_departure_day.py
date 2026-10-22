"""Enforce one departure per tour calendar day.

Revision ID: 20261022_0037
Revises: 20261022_0036
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0037"
down_revision = "20261022_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tour_calendar") as batch_op:
        batch_op.add_column(sa.Column("tour_date_day", sa.Date(), nullable=True))

    op.execute("UPDATE tour_calendar SET tour_date_day = DATE(tour_date)")
    duplicate = op.get_bind().execute(sa.text("""
        SELECT tour_id, tour_date_day
        FROM tour_calendar
        GROUP BY tour_id, tour_date_day
        HAVING COUNT(*) > 1
        LIMIT 1
    """)).first()
    if duplicate:
        raise RuntimeError(
            "Cannot enforce one departure per day: duplicate tour_calendar rows exist "
            f"for tour_id={duplicate[0]}, date={duplicate[1]}. Resolve the duplicate rows before retrying."
        )

    with op.batch_alter_table("tour_calendar") as batch_op:
        batch_op.alter_column("tour_date_day", existing_type=sa.Date(), nullable=False)
        batch_op.create_unique_constraint("uq_tour_calendar_departure_day", ["tour_id", "tour_date_day"])


def downgrade() -> None:
    with op.batch_alter_table("tour_calendar") as batch_op:
        batch_op.drop_constraint("uq_tour_calendar_departure_day", type_="unique")
        batch_op.drop_column("tour_date_day")
