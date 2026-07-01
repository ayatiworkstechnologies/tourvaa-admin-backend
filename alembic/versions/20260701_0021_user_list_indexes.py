"""Add indexes for user list filtering/sorting

Revision ID: 20260701_0021
Revises: 20260624_0020
Create Date: 2026-07-01
"""
from alembic import op
from sqlalchemy import inspect

revision = "20260701_0021"
down_revision = "20260624_0020"
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_users_role_id", "users", ["role_id"]),
    ("ix_users_is_active", "users", ["is_active"]),
    ("ix_users_approval_status", "users", ["approval_status"]),
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
