"""Add countries.flag_emoji so the country flag is stored once in the
database instead of being derived from a hard-coded, ~25-country name
lookup in the frontend. The value is a Unicode regional-indicator pair
derived from the ISO-2 country code and is backfilled here for every
existing row, so the column is populated even without re-running the
geo seed.

Revision ID: 20260918_0105
Revises: 20260917_0104
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260918_0105"
down_revision = "20260917_0104"
branch_labels = None
depends_on = None

TABLE = "countries"
COLUMN = "flag_emoji"


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, TABLE, COLUMN):
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.String(length=16), nullable=False, server_default=""),
        )

    # Backfill from the ISO-2 code: each letter maps to its regional
    # indicator symbol (U+1F1E6 + offset from 'A'), which is how a flag
    # emoji is composed. Done in SQL so it applies to existing databases
    # without needing the seeder.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT id, country_code FROM {TABLE} WHERE {COLUMN} = '' OR {COLUMN} IS NULL")
    ).fetchall()
    for row_id, code in rows:
        flag = _flag_from_iso2(code or "")
        if flag:
            conn.execute(
                sa.text(f"UPDATE {TABLE} SET {COLUMN} = :f WHERE id = :i"),
                {"f": flag, "i": row_id},
            )


def _flag_from_iso2(code: str) -> str:
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
