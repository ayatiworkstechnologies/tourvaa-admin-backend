"""add suppliers.onboarding_completed_at

Tracks whether a supplier has completed the first-login onboarding wizard
(src/app/supplier/onboarding). Null means the wizard should be shown on
next login - see supplier/layout.tsx's redirect check.

Revision ID: 20260821_0080
Revises: 20260821_0079
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0080"
down_revision = "20260821_0079"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "suppliers", "onboarding_completed_at"):
        op.add_column("suppliers", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "suppliers", "onboarding_completed_at"):
        op.drop_column("suppliers", "onboarding_completed_at")
