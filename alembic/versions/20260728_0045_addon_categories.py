"""add category to tour_optional_activities/tour_accommodation_extras/tour_extensions

Lets customer-facing add-ons be grouped by real named types (pickup, room
upgrade, dining, insurance, etc.) instead of the current flat
Accommodation/Activities/Extensions three-bucket split.

Revision ID: 20260728_0045
Revises: 20260728_0044
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0045"
down_revision = "20260728_0044"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("tour_optional_activities", "category"):
        op.add_column("tour_optional_activities", sa.Column("category", sa.String(length=30), nullable=False, server_default="other"))
    if not _has_column("tour_accommodation_extras", "category"):
        op.add_column("tour_accommodation_extras", sa.Column("category", sa.String(length=30), nullable=False, server_default="room_upgrade"))
    if not _has_column("tour_extensions", "category"):
        op.add_column("tour_extensions", sa.Column("category", sa.String(length=30), nullable=False, server_default="other"))


def downgrade():
    if _has_column("tour_extensions", "category"):
        op.drop_column("tour_extensions", "category")
    if _has_column("tour_accommodation_extras", "category"):
        op.drop_column("tour_accommodation_extras", "category")
    if _has_column("tour_optional_activities", "category"):
        op.drop_column("tour_optional_activities", "category")
