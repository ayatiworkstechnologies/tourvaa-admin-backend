"""add affiliate_documents.rejection_reason

Parity with SupplierDocument/AgentDocument, needed for admin
reject-with-reason on affiliate document review.

Revision ID: 20260825_0084
Revises: 20260824_0083
"""

import sqlalchemy as sa
from alembic import op

revision = "20260825_0084"
down_revision = "20260824_0083"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "affiliate_documents", "rejection_reason"):
        op.add_column("affiliate_documents", sa.Column("rejection_reason", sa.String(255), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "affiliate_documents", "rejection_reason"):
        op.drop_column("affiliate_documents", "rejection_reason")
