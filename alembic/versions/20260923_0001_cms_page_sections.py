"""Modern section-builder template for the generic CMS Pages tool.

Adds a nullable `sections` JSON column to cms_pages: an ordered list of
typed content blocks (hero, text, image_text, cards, cta) that the admin
Pages builder lets an operator construct freely for any page, rendered with
real design on the public site instead of the plain `content` HTML textarea.
NULL/empty (every existing row) means "no sections configured" -- the page
keeps rendering from the legacy `content` field exactly as before.

Revision ID: 20260923_0001
Revises: 20260922_0117
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0001"
down_revision = "20260922_0117"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("cms_pages")}
    if "sections" not in cols:
        op.add_column("cms_pages", sa.Column("sections", sa.JSON(), nullable=True))


def downgrade():
    pass
