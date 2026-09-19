"""Store agents.discount_value / commission_request_value as DECIMAL(12,2).

Both hold either a fixed currency amount or a percentage (depending on the
adjacent *_type column) that is later multiplied into booking totals, so they
should not be binary floats. Values are rounded to 2 decimals.

Revision ID: 20260919_0108
Revises: 20260919_0107
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260919_0108"
down_revision = "20260919_0107"
branch_labels = None
depends_on = None

# (column, nullable, server_default)
COLUMNS = [
    ("discount_value", False, "0"),
    ("commission_request_value", True, None),
]


def _existing() -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns("agents")}


def _alter(name: str, nullable: bool, default: str | None, *, to_decimal: bool) -> None:
    op.alter_column(
        "agents",
        name,
        existing_type=sa.Float() if to_decimal else sa.Numeric(12, 2),
        type_=sa.Numeric(12, 2) if to_decimal else sa.Float(),
        existing_nullable=nullable,
        existing_server_default=sa.text(default) if default is not None else None,
        server_default=sa.text(default) if default is not None else None,
    )


def upgrade() -> None:
    present = _existing()
    for name, nullable, default in COLUMNS:
        if name in present:
            op.execute(sa.text(f"UPDATE agents SET {name} = ROUND({name}, 2) WHERE {name} IS NOT NULL"))
            _alter(name, nullable, default, to_decimal=True)


def downgrade() -> None:
    present = _existing()
    for name, nullable, default in COLUMNS:
        if name in present:
            _alter(name, nullable, default, to_decimal=False)
