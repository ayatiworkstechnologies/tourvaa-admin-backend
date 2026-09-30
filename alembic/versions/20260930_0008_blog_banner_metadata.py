"""Add accessible banner metadata to CMS blogs.

Revision ID: 20260930_0008
Revises: 20260929_0007
"""

from alembic import op
import sqlalchemy as sa

revision = "20260930_0008"
down_revision = "20260929_0007"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cms_blogs") as batch:
        batch.add_column(sa.Column("banner_title", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("banner_alt", sa.String(length=300), nullable=True))


def downgrade():
    with op.batch_alter_table("cms_blogs") as batch:
        batch.drop_column("banner_alt")
        batch.drop_column("banner_title")
