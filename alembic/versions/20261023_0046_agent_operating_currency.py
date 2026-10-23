"""Store an administrator-selected operating currency for agents.

Revision ID: 20261023_0046
Revises: 20261023_0045
"""

from alembic import op
import sqlalchemy as sa


revision = "20261023_0046"
down_revision = "20261023_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("currency", sa.String(length=10), nullable=True))
    # Preserve a sensible value for existing agents instead of displaying the
    # old USD-only UI fallback. Administrators can still override this later.
    op.execute(
        "UPDATE agents, countries "
        "SET agents.currency = countries.currency_code "
        "WHERE agents.country_id = countries.id "
        "AND agents.currency IS NULL "
        "AND countries.currency_code IS NOT NULL "
        "AND countries.currency_code != ''"
    )


def downgrade() -> None:
    op.drop_column("agents", "currency")
