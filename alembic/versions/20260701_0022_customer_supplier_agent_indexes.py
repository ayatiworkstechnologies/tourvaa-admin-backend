"""Add indexes for customer/supplier/agent list filtering/sorting

Revision ID: 20260701_0022
Revises: 20260701_0021
Create Date: 2026-07-01
"""
from alembic import op
from sqlalchemy import inspect

revision = "20260701_0022"
down_revision = "20260701_0021"
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_customers_status", "customers", ["status"]),
    ("ix_customers_created_at", "customers", ["created_at"]),
    ("ix_suppliers_status", "suppliers", ["status"]),
    ("ix_suppliers_created_at", "suppliers", ["created_at"]),
    ("ix_agents_status", "agents", ["status"]),
    ("ix_agents_created_at", "agents", ["created_at"]),
]


def _existing_index_names(table: str) -> set[str]:
    return {ix["name"] for ix in inspect(op.get_bind()).get_indexes(table)}


def upgrade():
    for name, table, columns in INDEXES:
        if name not in _existing_index_names(table):
            op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in INDEXES:
        if name in _existing_index_names(table):
            op.drop_index(name, table_name=table)
