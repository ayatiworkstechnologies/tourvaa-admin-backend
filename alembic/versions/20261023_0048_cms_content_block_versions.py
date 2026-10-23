"""Add optimistic-concurrency versions to generic CMS content blocks.

Revision ID: 20261023_0048
Revises: 20261023_0047
"""

from alembic import op
import sqlalchemy as sa


revision = "20261023_0048"
down_revision = "20261023_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cms_homepage_content_blocks",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("cms_homepage_content_blocks", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("cms_homepage_content_blocks", "version")
