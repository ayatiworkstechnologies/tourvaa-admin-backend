"""add tour_accommodation_extras.image

Client feedback ("Pricing & Tours Feedback" doc, page 16): the public
add-ons section should show image-based cards per category. Optional
activities already have an `image` column; accommodation extras didn't -
this brings them to parity. Extensions link to another full Tour
(extension_tour_id) and reuse that tour's own banner_image instead of a
separate field.

Revision ID: 20260818_0070
Revises: 20260818_0069
"""

import sqlalchemy as sa
from alembic import op

revision = "20260818_0070"
down_revision = "20260818_0069"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "tour_accommodation_extras", "image"):
        op.add_column("tour_accommodation_extras", sa.Column("image", sa.String(255), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "tour_accommodation_extras", "image"):
        op.drop_column("tour_accommodation_extras", "image")
