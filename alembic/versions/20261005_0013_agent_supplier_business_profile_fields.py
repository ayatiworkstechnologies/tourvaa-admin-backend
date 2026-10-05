"""Add business identity fields to agent and supplier profiles."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261005_0013"
down_revision = "20261005_0012"
branch_labels = None
depends_on = None


def upgrade():
    specs = {
        "agent_business_info": [
            sa.Column("trading_name", sa.String(150), nullable=False, server_default=""),
            sa.Column("business_email", sa.String(150), nullable=False, server_default=""),
            sa.Column("website_url", sa.String(255), nullable=False, server_default=""),
            sa.Column("business_registration_number", sa.String(100), nullable=False, server_default=""),
        ],
        "supplier_business_info": [
            sa.Column("trading_name", sa.String(150), nullable=False, server_default=""),
            sa.Column("business_email", sa.String(150), nullable=False, server_default=""),
            sa.Column("website_url", sa.String(255), nullable=False, server_default=""),
        ],
    }
    for table, columns in specs.items():
        existing = {column["name"] for column in inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade():
    for table, names in (("agent_business_info", ("business_registration_number", "website_url", "business_email", "trading_name")), ("supplier_business_info", ("website_url", "business_email", "trading_name"))):
        with op.batch_alter_table(table) as batch:
            for name in names:
                batch.drop_column(name)
