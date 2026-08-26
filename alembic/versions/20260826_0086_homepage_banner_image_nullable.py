"""make cms_homepage_banners.image nullable

A banner now needs at least one of image/video (enforced in
BannerPayload), not both - admins can create a video-only hero banner.

Revision ID: 20260826_0086
Revises: 20260826_0085
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0086"
down_revision = "20260826_0085"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("cms_homepage_banners", "image", existing_type=sa.String(255), nullable=True)


def downgrade():
    op.execute("UPDATE cms_homepage_banners SET image = '' WHERE image IS NULL")
    op.alter_column("cms_homepage_banners", "image", existing_type=sa.String(255), nullable=False)
