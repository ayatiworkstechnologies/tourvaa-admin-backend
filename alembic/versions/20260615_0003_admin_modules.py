"""admin modules

Revision ID: 20260615_0003
Revises: 20260615_0002
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260615_0003"
down_revision = "20260615_0002"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "admin_modules"):
        return

    op.create_table(
        "admin_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_admin_modules_id"), "admin_modules", ["id"], unique=False)
    op.create_index(op.f("ix_admin_modules_slug"), "admin_modules", ["slug"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "admin_modules"):
        return

    op.drop_index(op.f("ix_admin_modules_slug"), table_name="admin_modules")
    op.drop_index(op.f("ix_admin_modules_id"), table_name="admin_modules")
    op.drop_table("admin_modules")
