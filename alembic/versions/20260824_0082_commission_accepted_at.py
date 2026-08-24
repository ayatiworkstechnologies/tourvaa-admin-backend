"""add commission_accepted_at to suppliers, agents, affiliates

Tracks whether the user has clicked "Yes" on the mandatory commission-
consent popup shown right after login. Null blocks document upload /
general portal access - see supplier/agent/affiliate layout.tsx and the
new CommissionConsentModal.

Revision ID: 20260824_0082
Revises: 20260821_0081
"""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0082"
down_revision = "20260821_0081"
branch_labels = None
depends_on = None

TABLES = ["suppliers", "agents", "affiliates"]


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in TABLES:
        if not _has_column(inspector, table, "commission_accepted_at"):
            op.add_column(table, sa.Column("commission_accepted_at", sa.DateTime(timezone=True), nullable=True))

    # affiliate_default_commission_value existed before this change with
    # is_public=False (services.settings.DEFAULT_SETTINGS only inserts
    # missing keys, it never updates existing rows) - flip any row already
    # seeded on this install so the new commission-consent popup can read it
    # via GET /settings/public the same way suppliers already do. Uses a
    # SQLAlchemy Core table (not a raw boolean literal) so it works
    # identically on both sqlite and postgres.
    if "app_settings" in inspector.get_table_names():
        app_settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("is_public", sa.Boolean))
        op.execute(app_settings.update().where(app_settings.c.key == "affiliate_default_commission_value").values(is_public=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in TABLES:
        if _has_column(inspector, table, "commission_accepted_at"):
            op.drop_column(table, "commission_accepted_at")
