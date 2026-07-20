"""standardize platform currency defaults on USD

Revision ID: 20260720_0026
Revises: 20260708_0025
"""

from alembic import op
import sqlalchemy as sa

revision = "20260720_0026"
down_revision = "20260708_0025"
branch_labels = None
depends_on = None


def upgrade():
    settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.Text))
    op.execute(settings.update().where(settings.c.key.in_(["currency", "default_currency"])).values(value="USD"))


def downgrade():
    settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.Text))
    op.execute(settings.update().where(settings.c.key == "default_currency").values(value="INR"))
    op.execute(settings.update().where(settings.c.key == "currency").values(value="NZD"))
