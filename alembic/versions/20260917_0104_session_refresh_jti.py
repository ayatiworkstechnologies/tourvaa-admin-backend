"""Add user_sessions.current_refresh_jti to support refresh-token rotation
with reuse detection: each successful /auth/refresh-token call now issues a
refresh token carrying a fresh jti and records it on the session, so a
previously-rotated (stolen or replayed) refresh token can be recognized and
the session revoked instead of silently accepted until its own expiry.

Revision ID: 20260917_0104
Revises: 20260917_0103
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260917_0104"
down_revision = "20260917_0103"
branch_labels = None
depends_on = None

TABLE = "user_sessions"
COLUMN = "current_refresh_jti"


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, TABLE, COLUMN):
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(64), nullable=True))


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
