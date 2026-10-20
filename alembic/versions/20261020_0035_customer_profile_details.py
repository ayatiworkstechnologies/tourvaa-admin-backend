"""Persist customer travel-profile details.

Revision ID: 20261020_0035
Revises: 20261020_0034
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0035"
down_revision = "20261020_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("nationality", sa.String(length=100), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("passport_number", sa.String(length=100), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("passport_expiry", sa.String(length=40), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("frequent_flyer", sa.String(length=100), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("preferred_airline", sa.String(length=100), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("emergency_name", sa.String(length=150), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("emergency_relation", sa.String(length=100), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("emergency_phone", sa.String(length=30), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("emergency_email", sa.String(length=150), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        for column in ("emergency_email", "emergency_phone", "emergency_relation", "emergency_name", "preferred_airline", "frequent_flyer", "passport_expiry", "passport_number", "nationality"):
            batch_op.drop_column(column)
