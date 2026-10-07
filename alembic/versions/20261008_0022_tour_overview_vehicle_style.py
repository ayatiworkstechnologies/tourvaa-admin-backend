"""Add a configurable vehicle style to tour overviews.

Revision ID: 20261008_0022
Revises: 20261007_0021
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261008_0022"
down_revision = "20261007_0021"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("tour_overviews")}
    if "vehicle_style" not in columns:
        op.add_column(
            "tour_overviews",
            sa.Column("vehicle_style", sa.String(length=100), nullable=False, server_default=""),
        )
        op.execute(
            """
            UPDATE tour_overviews
            SET vehicle_style = CASE
                WHEN (SELECT max_group_size FROM tours WHERE tours.id = tour_overviews.tour_id) <= 4 THEN 'Private car'
                WHEN (SELECT max_group_size FROM tours WHERE tours.id = tour_overviews.tour_id) <= 6 THEN 'Mini cab'
                WHEN (SELECT max_group_size FROM tours WHERE tours.id = tour_overviews.tour_id) <= 12 THEN 'Minivan'
                WHEN (SELECT max_group_size FROM tours WHERE tours.id = tour_overviews.tour_id) <= 20 THEN 'Mini coach'
                WHEN (SELECT max_group_size FROM tours WHERE tours.id = tour_overviews.tour_id) > 20 THEN 'Coach'
                ELSE ''
            END
            """
        )


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("tour_overviews")}
    if "vehicle_style" in columns:
        op.drop_column("tour_overviews", "vehicle_style")
