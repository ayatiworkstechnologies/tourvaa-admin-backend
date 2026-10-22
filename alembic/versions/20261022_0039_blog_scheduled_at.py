"""Add scheduled_at column to cms_blogs.

Revision ID: 20261022_0039
Revises: 20261022_0038
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0039"
down_revision = "20261022_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cms_blogs") as batch_op:
        batch_op.add_column(sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("cms_blogs") as batch_op:
        batch_op.drop_column("scheduled_at")
