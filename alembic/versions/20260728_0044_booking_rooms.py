"""add bookings.no_of_rooms

Infants (no_of_infants) already existed end-to-end but was never collected by
the booking wizard - that's a frontend-only fix. Room requirement is a
genuinely new field.

Revision ID: 20260728_0044
Revises: 20260727_0043
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0044"
down_revision = "20260727_0043"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("bookings", "no_of_rooms"):
        op.add_column("bookings", sa.Column("no_of_rooms", sa.Integer(), nullable=True))


def downgrade():
    if _has_column("bookings", "no_of_rooms"):
        op.drop_column("bookings", "no_of_rooms")
