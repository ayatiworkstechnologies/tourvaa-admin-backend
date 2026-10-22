"""Allow half-star ratings for CMS testimonials.

Revision ID: 20261022_0038
Revises: 20261022_0037
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0038"
down_revision = "20261022_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cms_customer_reviews") as batch_op:
        batch_op.alter_column(
            "rating",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("cms_customer_reviews") as batch_op:
        batch_op.alter_column(
            "rating",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
