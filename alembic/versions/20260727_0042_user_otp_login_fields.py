"""add users.otp_code_hash/otp_expires_at/otp_attempts for OTP checkout login

Adds email-only OTP login to the customer booking checkout flow, alongside
the existing password + email-verification-link auth. Mirrors the existing
email_verification_token/_expires_at hash+expiry pattern on the same table,
just with a shorter-lived numeric code instead of an opaque link token.

Revision ID: 20260727_0042
Revises: 20260727_0041
"""

import sqlalchemy as sa
from alembic import op

revision = "20260727_0042"
down_revision = "20260727_0041"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("users", "otp_code_hash"):
        op.add_column("users", sa.Column("otp_code_hash", sa.String(length=255), nullable=True))
    if not _has_column("users", "otp_expires_at"):
        op.add_column("users", sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("users", "otp_attempts"):
        op.add_column("users", sa.Column("otp_attempts", sa.Integer(), nullable=True, server_default="0"))


def downgrade():
    if _has_column("users", "otp_attempts"):
        op.drop_column("users", "otp_attempts")
    if _has_column("users", "otp_expires_at"):
        op.drop_column("users", "otp_expires_at")
    if _has_column("users", "otp_code_hash"):
        op.drop_column("users", "otp_code_hash")
