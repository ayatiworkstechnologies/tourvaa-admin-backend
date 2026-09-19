"""Store the tour-level money columns as DECIMAL(12,2) instead of FLOAT.

The per-slab pricing tables already use DECIMAL; these six columns on
`tours` were still binary floats, so a stored price such as 19.99 could come
back as 19.989999771... Percentages (tax, gateway fee, deposit) stay FLOAT:
they are rates, not currency amounts.

Existing values are rounded to 2 decimals by the column conversion.

Revision ID: 20260919_0107
Revises: 20260918_0106
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260919_0107"
down_revision = "20260918_0106"
branch_labels = None
depends_on = None

MONEY_COLUMNS = [
    "price_start_per_person",
    "offer_price",
    "infant_price",
    "single_supplement",
    "service_fee",
    "booking_deposit",
]


def _existing_columns() -> dict:
    return {c["name"]: c for c in inspect(op.get_bind()).get_columns("tours")}


def upgrade() -> None:
    columns = _existing_columns()
    for name in MONEY_COLUMNS:
        if name not in columns:
            continue
        op.execute(sa.text(f"UPDATE tours SET {name} = ROUND({name}, 2) WHERE {name} IS NOT NULL"))
        op.alter_column(
            "tours",
            name,
            existing_type=sa.Float(),
            type_=sa.Numeric(12, 2),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
            server_default=sa.text("0"),
        )


def downgrade() -> None:
    columns = _existing_columns()
    for name in MONEY_COLUMNS:
        if name not in columns:
            continue
        op.alter_column(
            "tours",
            name,
            existing_type=sa.Numeric(12, 2),
            type_=sa.Float(),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
            server_default=sa.text("0"),
        )
