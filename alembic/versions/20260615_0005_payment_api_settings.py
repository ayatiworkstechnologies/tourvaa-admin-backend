"""payment api settings

Revision ID: 20260615_0005
Revises: 20260615_0004
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260615_0005"
down_revision = "20260615_0004"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "payment_settings"):
        op.create_table(
            "payment_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider_name", sa.String(length=100), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("public_key", sa.Text(), nullable=True),
            sa.Column("secret_key", sa.Text(), nullable=True),
            sa.Column("surcharge_percentage", sa.String(length=20), nullable=False, server_default="0"),
            sa.Column("mode", sa.String(length=20), nullable=False, server_default="test"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider_name"),
        )
        op.create_index(op.f("ix_payment_settings_id"), "payment_settings", ["id"], unique=False)
        op.create_index(op.f("ix_payment_settings_provider_name"), "payment_settings", ["provider_name"], unique=False)

    if not _has_table(inspector, "api_settings"):
        op.create_table(
            "api_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("api_name", sa.String(length=100), nullable=False),
            sa.Column("api_key", sa.Text(), nullable=True),
            sa.Column("api_secret", sa.Text(), nullable=True),
            sa.Column("api_url", sa.Text(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("api_name"),
        )
        op.create_index(op.f("ix_api_settings_id"), "api_settings", ["id"], unique=False)
        op.create_index(op.f("ix_api_settings_api_name"), "api_settings", ["api_name"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "api_settings"):
        op.drop_index(op.f("ix_api_settings_api_name"), table_name="api_settings")
        op.drop_index(op.f("ix_api_settings_id"), table_name="api_settings")
        op.drop_table("api_settings")

    if _has_table(inspector, "payment_settings"):
        op.drop_index(op.f("ix_payment_settings_provider_name"), table_name="payment_settings")
        op.drop_index(op.f("ix_payment_settings_id"), table_name="payment_settings")
        op.drop_table("payment_settings")
