"""audit log json columns

Revision ID: 20260615_0002
Revises: 20260615_0001
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260615_0002"
down_revision = "20260615_0001"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    if not _has_table(inspector, table_name):
        return False

    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "audit_logs"):
        return

    with op.batch_alter_table("audit_logs") as batch_op:
        if _has_column(inspector, "audit_logs", "old_values"):
            batch_op.alter_column(
                "old_values",
                existing_type=sa.Text(),
                type_=sa.JSON(),
                existing_nullable=True,
            )
        if _has_column(inspector, "audit_logs", "new_values"):
            batch_op.alter_column(
                "new_values",
                existing_type=sa.Text(),
                type_=sa.JSON(),
                existing_nullable=True,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "audit_logs"):
        return

    with op.batch_alter_table("audit_logs") as batch_op:
        if _has_column(inspector, "audit_logs", "old_values"):
            batch_op.alter_column(
                "old_values",
                existing_type=sa.JSON(),
                type_=sa.Text(),
                existing_nullable=True,
            )
        if _has_column(inspector, "audit_logs", "new_values"):
            batch_op.alter_column(
                "new_values",
                existing_type=sa.JSON(),
                type_=sa.Text(),
                existing_nullable=True,
            )
