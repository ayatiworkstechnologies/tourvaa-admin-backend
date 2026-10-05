"""Add complete billing details to supplier invoicing."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261005_0012"
down_revision = "20261005_0011"
branch_labels = None
depends_on = None


def upgrade():
    existing = {column["name"] for column in inspect(op.get_bind()).get_columns("supplier_invoicing")}
    columns = [
        sa.Column("preferred_payment_method", sa.String(30), nullable=False, server_default=""),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("billing_city", sa.String(100), nullable=False, server_default=""),
        sa.Column("billing_state", sa.String(100), nullable=False, server_default=""),
        sa.Column("billing_postal_code", sa.String(30), nullable=False, server_default=""),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("supplier_invoicing", column)


def downgrade():
    with op.batch_alter_table("supplier_invoicing") as batch:
        for name in ("billing_postal_code", "billing_state", "billing_city", "billing_address", "preferred_payment_method"):
            batch.drop_column(name)
