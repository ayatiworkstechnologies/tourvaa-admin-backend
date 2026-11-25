"""Add category, og_image and related_tour_ids to cms_blogs.

Revision ID: 20261124_0056
Revises: 20261103_0055
Create Date: 2026-11-24

Blog create was 500ing: BlogPayload accepts category, og_image and
related_tour_ids, but the Blog model and cms_blogs table had none of
them, so Blog(**payload) raised TypeError.
"""
from alembic import op
import sqlalchemy as sa


revision = "20261124_0056"
down_revision = "20261120_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cms_blogs", sa.Column("category", sa.String(120), nullable=True))
    op.add_column("cms_blogs", sa.Column("og_image", sa.String(255), nullable=True))
    op.add_column("cms_blogs", sa.Column("related_tour_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cms_blogs", "related_tour_ids")
    op.drop_column("cms_blogs", "og_image")
    op.drop_column("cms_blogs", "category")
