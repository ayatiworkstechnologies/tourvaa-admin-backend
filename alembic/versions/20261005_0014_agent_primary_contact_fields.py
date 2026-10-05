"""Add structured primary contact fields for agent profiles."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261005_0014"
down_revision = "20261005_0013"
branch_labels = None
depends_on = None

def upgrade():
    existing = {column["name"] for column in inspect(op.get_bind()).get_columns("agent_contacts")}
    for column in (sa.Column("first_name", sa.String(75), nullable=False, server_default=""), sa.Column("last_name", sa.String(75), nullable=False, server_default=""), sa.Column("preferred_contact_method", sa.String(20), nullable=False, server_default="")):
        if column.name not in existing:
            op.add_column("agent_contacts", column)

def downgrade():
    with op.batch_alter_table("agent_contacts") as batch:
        batch.drop_column("preferred_contact_method")
        batch.drop_column("last_name")
        batch.drop_column("first_name")
