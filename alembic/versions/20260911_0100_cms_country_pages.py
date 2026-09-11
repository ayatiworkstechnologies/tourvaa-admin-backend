"""Add cms_country_pages so admins can override the hero banner and
showcase panel copy/images, plus SEO title/description, for each country's
dynamic /tours/{country} landing page - see CountryPage in
app/models/website_cms.py.

Revision ID: 20260911_0100
Revises: 20260911_0099
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260911_0100"
down_revision = "20260911_0099"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "cms_country_pages"):
        op.create_table(
            "cms_country_pages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=False, unique=True, index=True),
            sa.Column("hero_title", sa.String(200), nullable=True),
            sa.Column("hero_description", sa.Text(), nullable=True),
            sa.Column("hero_image", sa.String(255), nullable=True),
            sa.Column("showcase_title", sa.String(200), nullable=True),
            sa.Column("showcase_description", sa.Text(), nullable=True),
            sa.Column("showcase_image", sa.String(255), nullable=True),
            sa.Column("seo_title", sa.String(200), nullable=True),
            sa.Column("seo_description", sa.String(400), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_country_pages"):
        op.drop_table("cms_country_pages")
