"""add accommodation to tour_itineraries

The public API contract already exposed an `accommodation` field per
itinerary day, but it was hardcoded to an empty string - no such column
existed anywhere. This adds the real column so the "Where You'll Stay"
tour-detail section can show actual per-day accommodation names.

Revision ID: 20260728_0047
Revises: 20260728_0046
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0047"
down_revision = "20260728_0046"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("tour_itineraries", "accommodation"):
        op.add_column("tour_itineraries", sa.Column("accommodation", sa.String(length=255), nullable=True, server_default=""))


def downgrade():
    if _has_column("tour_itineraries", "accommodation"):
        op.drop_column("tour_itineraries", "accommodation")
