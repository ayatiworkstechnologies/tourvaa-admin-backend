"""Add the per-tour guide style setting used by the itinerary editor.

Revision ID: 20261007_0019
Revises: 20261007_0018
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261007_0019"
down_revision = "20261007_0018"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("tour_overviews")}
    if "guide_style" not in columns:
        op.add_column("tour_overviews", sa.Column("guide_style", sa.String(length=50), nullable=False, server_default=""))


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("tour_overviews")}
    if "guide_style" in columns:
        op.drop_column("tour_overviews", "guide_style")
