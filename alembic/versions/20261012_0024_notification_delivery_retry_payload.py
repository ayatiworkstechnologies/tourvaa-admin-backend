"""retain lifecycle delivery payloads for finite SMTP retries

Revision ID: 20261012_0024
Revises: 20261009_0023
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261012_0024"
down_revision = "20261009_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notification_deliveries", sa.Column("payload_json", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("notification_deliveries", "payload_json")
