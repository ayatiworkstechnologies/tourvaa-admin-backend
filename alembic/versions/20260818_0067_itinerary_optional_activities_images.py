"""add tour_itineraries.optional_activities and .images

Client feedback ("Pricing & Tours Feedback" doc, page 8): each itinerary day
should show a separate "Optional Activities" list alongside "Included
Activities", and a small image carousel rather than a single cover image.

  - optional_activities: free-text, same format/parsing as the existing
    `activities` column (newline/comma separated).
  - images: JSON-encoded list of image paths for the day's carousel. The
    existing `image`/`image_alt_text` columns stay as the single cover/
    fallback image for backward compatibility (e.g. itinerary_pdf.py).

Revision ID: 20260818_0067
Revises: 20260813_0066
"""

import sqlalchemy as sa
from alembic import op

revision = "20260818_0067"
down_revision = "20260813_0066"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # MySQL rejects a literal DEFAULT on TEXT/BLOB columns - backfill via
    # UPDATE instead (mirrors the empty-string/"[]" fallback already handled
    # in Python at read time by services.tours._ser_itinerary).
    if not _has_column(inspector, "tour_itineraries", "optional_activities"):
        op.add_column("tour_itineraries", sa.Column("optional_activities", sa.Text(), nullable=True))
    if not _has_column(inspector, "tour_itineraries", "images"):
        op.add_column("tour_itineraries", sa.Column("images", sa.Text(), nullable=True))
        op.execute("UPDATE tour_itineraries SET images = '[]' WHERE images IS NULL")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "tour_itineraries", "images"):
        op.drop_column("tour_itineraries", "images")
    if _has_column(inspector, "tour_itineraries", "optional_activities"):
        op.drop_column("tour_itineraries", "optional_activities")
