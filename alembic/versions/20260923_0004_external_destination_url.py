"""Store Viator's own affiliate destination URL (destinationUrl, which already
carries pid/mcid) so the homepage can hand off straight to viator.com.

Revision ID: 20260923_0004
Revises: 20260923_0003
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0004"
down_revision = "20260923_0003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("external_destination_mappings")}
    if "provider_destination_url" not in cols:
        op.add_column("external_destination_mappings", sa.Column("provider_destination_url", sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("external_destination_mappings")}
    if "provider_destination_url" in cols:
        op.drop_column("external_destination_mappings", "provider_destination_url")
