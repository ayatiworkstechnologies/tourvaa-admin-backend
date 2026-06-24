"""Add email verification fields to users

Revision ID: 20260621_0017
Revises: 20260621_0016
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260621_0017"
down_revision = "20260621_0016"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade():
    if not _has_column("users", "email_verified_at"):
        op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("users", "email_verification_token"):
        op.add_column("users", sa.Column("email_verification_token", sa.String(length=255), nullable=True))
    if not _has_column("users", "email_verification_expires_at"):
        op.add_column("users", sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    if _has_column("users", "email_verification_expires_at"):
        op.drop_column("users", "email_verification_expires_at")
    if _has_column("users", "email_verification_token"):
        op.drop_column("users", "email_verification_token")
    if _has_column("users", "email_verified_at"):
        op.drop_column("users", "email_verified_at")
