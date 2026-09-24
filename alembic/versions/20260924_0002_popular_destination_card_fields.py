"""Add editable rating and package count to popular destinations.

Revision ID: 20260924_0002
Revises: 20260924_0001
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0002"
down_revision = "20260924_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cms_popular_destinations",
        sa.Column("rating", sa.Float(), nullable=True),
    )
    op.add_column(
        "cms_popular_destinations",
        sa.Column("package_count", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("cms_popular_destinations", "package_count")
    op.drop_column("cms_popular_destinations", "rating")
