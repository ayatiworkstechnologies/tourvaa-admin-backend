"""add users.failed_login_attempts / users.locked_until

Password login had no account-level brute-force protection - only IP-based
rate limiting (see app/utils/ratelimit.py) and OTP login (which already has
otp_attempts). This adds a per-account failed-attempt counter and a lockout
timestamp so repeated bad passwords against one account get throttled
independent of the caller's IP.

Revision ID: 20260819_0071
Revises: 20260818_0070
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0071"
down_revision = "20260818_0070"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "users", "failed_login_attempts"):
        op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column(inspector, "users", "locked_until"):
        op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "users", "locked_until"):
        op.drop_column("users", "locked_until")
    if _has_column(inspector, "users", "failed_login_attempts"):
        op.drop_column("users", "failed_login_attempts")
