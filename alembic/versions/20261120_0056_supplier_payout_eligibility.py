"""Record actual booking completion for supplier payout eligibility.

Revision ID: 20261120_0056
Revises: 20261103_0055
"""

from alembic import op
import sqlalchemy as sa


revision = "20261120_0056"
down_revision = "20261103_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("bookings")}
    indexes = {index["name"] for index in inspector.get_indexes("bookings")}

    if "completed_at" not in columns:
        op.add_column("bookings", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_bookings_completed_at" not in indexes:
        op.create_index("ix_bookings_completed_at", "bookings", ["completed_at"], unique=False)

    # Use the earliest recorded transition to completed. Leave rows without
    # completion history unset so they cannot be assigned an invented date.
    bookings = sa.table(
        "bookings",
        sa.column("id", sa.Integer),
        sa.column("booking_status", sa.String),
        sa.column("completed_at", sa.DateTime(timezone=True)),
    )
    history = sa.table(
        "booking_status_history",
        sa.column("booking_id", sa.Integer),
        sa.column("new_status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    completion_time = (
        sa.select(sa.func.min(history.c.created_at))
        .where(history.c.booking_id == bookings.c.id)
        .where(sa.func.lower(history.c.new_status) == "completed")
        .scalar_subquery()
    )
    op.execute(
        bookings.update()
        .where(bookings.c.booking_status == "completed")
        .where(bookings.c.completed_at.is_(None))
        .where(completion_time.is_not(None))
        .values(completed_at=completion_time)
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("bookings")}
    columns = {column["name"] for column in inspector.get_columns("bookings")}
    if "ix_bookings_completed_at" in indexes:
        op.drop_index("ix_bookings_completed_at", table_name="bookings")
    if "completed_at" in columns:
        op.drop_column("bookings", "completed_at")
