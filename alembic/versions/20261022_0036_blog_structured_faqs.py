"""Store blog FAQs separately from sanitised article content.

Revision ID: 20261022_0036
Revises: 20261020_0035
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0036"
down_revision = "20261020_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cms_blogs") as batch_op:
        batch_op.add_column(sa.Column("faqs", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("cms_blogs") as batch_op:
        batch_op.drop_column("faqs")
