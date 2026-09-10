"""Add cms_pages so admins can dynamically create pages (title/content/SEO,
an enable/disable status, and an optional footer section assignment) that
become real navigable pages and automatically appear as footer links when
published - see get_public_footer in app/services/website_cms.py.

Revision ID: 20260910_0096
Revises: 20260909_0095
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260910_0096"
down_revision = "20260909_0095"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "cms_pages"):
        op.create_table(
            "cms_pages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("slug", sa.String(220), nullable=False, unique=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("seo_title", sa.String(200), nullable=True),
            sa.Column("seo_description", sa.String(400), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("footer_section_id", sa.Integer(), sa.ForeignKey("cms_footer_sections.id"), nullable=True, index=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_pages"):
        op.drop_table("cms_pages")
