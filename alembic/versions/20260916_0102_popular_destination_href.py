"""Add href to cms_popular_destinations so admins can set an explicit
destination link (e.g. "/tours?country=Egypt") per country card in the
homepage "Countries Worth Exploring" section, instead of the frontend
always deriving the link from the country name.

Revision ID: 20260916_0102
Revises: 20260915_0101
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260916_0102"
down_revision = "20260915_0101"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "cms_popular_destinations", "href"):
        op.add_column("cms_popular_destinations", sa.Column("href", sa.String(500), nullable=True))


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "cms_popular_destinations", "href"):
        op.drop_column("cms_popular_destinations", "href")
