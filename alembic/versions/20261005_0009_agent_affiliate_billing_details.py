"""Add complete agent and affiliate bank and billing details.

Revision ID: 20261005_0009
Revises: 20260930_0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261005_0009"
down_revision = "20260930_0008"
branch_labels = None
depends_on = None


def _add_columns(table, bank_routing=False):
    # MySQL DDL is non-transactional.  A previous interrupted upgrade may
    # already have added one or more columns, so only add the fields that are
    # genuinely absent before continuing.
    existing = {column["name"] for column in inspect(op.get_bind()).get_columns(table)}

    def add_if_missing(column):
        if column.name not in existing:
            op.add_column(table, column)

    add_if_missing(sa.Column("preferred_payment_method", sa.String(30), nullable=False, server_default=""))
    if bank_routing:
        add_if_missing(sa.Column("bank_branch", sa.String(150), nullable=False, server_default=""))
        add_if_missing(sa.Column("swift_code", sa.String(50), nullable=False, server_default=""))
        add_if_missing(sa.Column("iban", sa.String(100), nullable=False, server_default=""))
    # MySQL does not allow defaults for TEXT/BLOB columns.  Existing profile
    # rows have no invoice address yet, therefore this remains nullable until
    # the profile owner completes those details.
    add_if_missing(sa.Column("billing_address", sa.Text(), nullable=True))
    add_if_missing(sa.Column("billing_city", sa.String(100), nullable=False, server_default=""))
    add_if_missing(sa.Column("billing_state", sa.String(100), nullable=False, server_default=""))
    add_if_missing(sa.Column("billing_postal_code", sa.String(30), nullable=False, server_default=""))

def upgrade():
    _add_columns("agent_invoicing")
    _add_columns("affiliate_invoicing", bank_routing=True)


def downgrade():
    for table, bank_routing in (("affiliate_invoicing", True), ("agent_invoicing", False)):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("billing_postal_code")
            batch.drop_column("billing_state")
            batch.drop_column("billing_city")
            batch.drop_column("billing_address")
            if bank_routing:
                batch.drop_column("iban")
                batch.drop_column("swift_code")
                batch.drop_column("bank_branch")
            batch.drop_column("preferred_payment_method")
