"""Store supplier bank country separately from billing country."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261006_0016"
down_revision = "20261005_0015"
branch_labels = None
depends_on = None


def upgrade():
    existing = {column["name"] for column in inspect(op.get_bind()).get_columns("supplier_invoicing")}
    if "bank_country_id" not in existing:
        op.add_column("supplier_invoicing", sa.Column("bank_country_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_supplier_invoicing_bank_country_id_countries",
            "supplier_invoicing",
            "countries",
            ["bank_country_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("supplier_invoicing") as batch:
        batch.drop_column("bank_country_id")
