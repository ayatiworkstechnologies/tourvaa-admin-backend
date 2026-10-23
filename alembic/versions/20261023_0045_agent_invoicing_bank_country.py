"""Store the country selected for an agent bank account.

Revision ID: 20261023_0045
Revises: 20261023_0044
"""

from alembic import op
import sqlalchemy as sa


revision = "20261023_0045"
down_revision = "20261023_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_invoicing",
        sa.Column("bank_country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_invoicing", "bank_country_id")
