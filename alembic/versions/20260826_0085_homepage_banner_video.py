"""add cms_homepage_banners.video

Optional hero video for the public homepage - when set, the frontend plays
this instead of the static image; `image` still serves as the <video>
poster frame and the fallback for browsers/crawlers that don't render video.

Revision ID: 20260826_0085
Revises: 20260825_0084
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0085"
down_revision = "20260825_0084"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "cms_homepage_banners", "video"):
        op.add_column("cms_homepage_banners", sa.Column("video", sa.String(255), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "cms_homepage_banners", "video"):
        op.drop_column("cms_homepage_banners", "video")
