"""add smtp_settings table

SMTP configuration previously lived only in environment variables, with no
way for an admin to change it without a deploy/restart. This adds a
single-row DB-backed config the Settings UI can edit; app/utils/mailer.py
falls back to the existing env vars when this table is empty or disabled.

Revision ID: 20260728_0048
Revises: 20260728_0047
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0048"
down_revision = "20260728_0047"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "smtp_settings"):
        op.create_table(
            "smtp_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("host", sa.String(length=255), nullable=True),
            sa.Column("port", sa.Integer(), nullable=False, server_default="465"),
            sa.Column("username", sa.String(length=255), nullable=True),
            sa.Column("password", sa.Text(), nullable=True),
            sa.Column("from_name", sa.String(length=150), nullable=False, server_default="Tourvaa"),
            sa.Column("from_email", sa.String(length=255), nullable=True),
            sa.Column("reply_to", sa.String(length=255), nullable=True),
            sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("use_starttls", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_smtp_settings_id"), "smtp_settings", ["id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "smtp_settings"):
        op.drop_index(op.f("ix_smtp_settings_id"), table_name="smtp_settings")
        op.drop_table("smtp_settings")
