"""Add a Currency master table (name/code/symbol) and a Supplier.currency
column, so a supplier's operating currency can be auto-derived from their
country and stored/overridden explicitly, instead of currency only ever
existing as a bare free-text code on Tour/Booking/Invoice/Ledger rows.

Revision ID: 20260909_0094
Revises: 20260908_0093
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260909_0094"
down_revision = "20260908_0093"
branch_labels = None
depends_on = None


# code, name, symbol - sourced from the frontend's existing CURRENCY_LIST
# (src/lib/utils/currency.ts) so the seeded master list matches what the UI
# already understood before this table existed.
_SEED_CURRENCIES = [
    ("USD", "US Dollar", "$"),
    ("EUR", "Euro", "€"),
    ("GBP", "British Pound", "£"),
    ("INR", "Indian Rupee", "₹"),
    ("AED", "UAE Dirham", "د.إ"),
    ("SAR", "Saudi Riyal", "﷼"),
    ("QAR", "Qatari Riyal", "﷼"),
    ("SGD", "Singapore Dollar", "S$"),
    ("AUD", "Australian Dollar", "A$"),
    ("CAD", "Canadian Dollar", "C$"),
    ("JPY", "Japanese Yen", "¥"),
    ("CNY", "Chinese Yuan", "¥"),
    ("THB", "Thai Baht", "฿"),
    ("MYR", "Malaysian Ringgit", "RM"),
    ("IDR", "Indonesian Rupiah", "Rp"),
    ("PHP", "Philippine Peso", "₱"),
    ("VND", "Vietnamese Dong", "₫"),
    ("ZAR", "South African Rand", "R"),
    ("NZD", "New Zealand Dollar", "NZ$"),
    ("CHF", "Swiss Franc", "CHF"),
    ("HKD", "Hong Kong Dollar", "HK$"),
    ("KRW", "South Korean Won", "₩"),
    ("LKR", "Sri Lankan Rupee", "Rs"),
    ("NPR", "Nepalese Rupee", "Rs"),
    ("BDT", "Bangladeshi Taka", "৳"),
    ("MVR", "Maldivian Rufiyaa", "Rf"),
]


def _has_table(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _has_column(inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade():
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, "currencies"):
        currencies_table = op.create_table(
            "currencies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("code", sa.String(10), nullable=False, unique=True),
            sa.Column("symbol", sa.String(10), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.bulk_insert(
            currencies_table,
            [{"name": name, "code": code, "symbol": symbol, "status": "active"} for code, name, symbol in _SEED_CURRENCIES],
        )

    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "suppliers", "currency"):
        op.add_column("suppliers", sa.Column("currency", sa.String(10), nullable=True))
        op.execute(
            "UPDATE suppliers, countries "
            "SET suppliers.currency = countries.currency_code "
            "WHERE suppliers.country_id = countries.id "
            "AND suppliers.currency IS NULL "
            "AND countries.currency_code IS NOT NULL "
            "AND countries.currency_code != ''"
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "suppliers", "currency"):
        op.drop_column("suppliers", "currency")

    inspector = inspect(op.get_bind())
    if _has_table(inspector, "currencies"):
        op.drop_table("currencies")
