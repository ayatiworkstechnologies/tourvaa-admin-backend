"""Add CMS-backed content for previously-hardcoded homepage sections:
handpicked tours (separate list from popular/trending tours), the
favourite-countries editorial list, and a generic key/JSON store for
one-off content blocks (hero trust badge + offer strip, About Tourvaa,
blog teaser banner, airport-transfers banner).

Revision ID: 20260908_0092
Revises: 20260903_0091
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260908_0092"
down_revision = "20260903_0091"
branch_labels = None
depends_on = None


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def upgrade():
    inspector = inspect(op.get_bind())

    if not _has_table(inspector, "cms_handpicked_tours"):
        op.create_table(
            "cms_handpicked_tours",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tour_id", sa.Integer(), sa.ForeignKey("tours.id"), nullable=False, index=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "cms_favourite_countries"):
        op.create_table(
            "cms_favourite_countries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=True, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("snippet", sa.Text(), nullable=True),
            sa.Column("image", sa.String(255), nullable=True),
            sa.Column("href", sa.String(500), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "cms_homepage_content_blocks"):
        op.create_table(
            "cms_homepage_content_blocks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(60), nullable=False, unique=True, index=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_homepage_content_blocks"):
        op.drop_table("cms_homepage_content_blocks")
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_favourite_countries"):
        op.drop_table("cms_favourite_countries")
    inspector = inspect(op.get_bind())
    if _has_table(inspector, "cms_handpicked_tours"):
        op.drop_table("cms_handpicked_tours")
