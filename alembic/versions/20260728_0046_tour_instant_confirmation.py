"""add tours.requires_supplier_confirmation

Lets a tour opt out of the supplier-acceptance wait: when False, a fully
paid booking with an assigned supplier goes straight to "confirmed" instead
of "pending_supplier_acceptance". Defaults True so every existing tour keeps
today's behavior unchanged.

Revision ID: 20260728_0046
Revises: 20260728_0045
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0046"
down_revision = "20260728_0045"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    if not _has_column("tours", "requires_supplier_confirmation"):
        op.add_column("tours", sa.Column("requires_supplier_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    if _has_column("tours", "requires_supplier_confirmation"):
        op.drop_column("tours", "requires_supplier_confirmation")
