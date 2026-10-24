"""Improve stock tour email action copy.

Revision ID: 20261024_0051
Revises: 20261024_0050
"""

from alembic import op
import sqlalchemy as sa


revision = "20261024_0051"
down_revision = "20261024_0050"
branch_labels = None
depends_on = None


def _replace_stock(key: str, old: str, new: str) -> None:
    templates = sa.table("email_templates", sa.column("key", sa.String()), sa.column("body", sa.Text()))
    op.execute(templates.update().where(templates.c.key == key).where(templates.c.body == old).values(body=new))


def upgrade() -> None:
    _replace_stock(
        "tour_submitted",
        "Your tour {{tour_name}} (version {{version}}) has been submitted to Tourvaa for review. {{login_url}}",
        "Your tour {{tour_name}} (version {{version}}) has been submitted to Tourvaa for review. Use the button below to view its current status.",
    )
    _replace_stock(
        "tour_reviewed",
        "Your tour {{tour_name}} (version {{version}}) was {{decision}}. {{reason}} {{login_url}}",
        "Your tour {{tour_name}} (version {{version}}) was {{decision}}.\n\n{{reason}}\n\nUse the button below to view the tour and any required next steps.",
    )


def downgrade() -> None:
    pass
