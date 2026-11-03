"""Store the OAuth provider used by a user account.

Revision ID: 20261103_0055
Revises: 20261028_0054
"""

from alembic import op
import sqlalchemy as sa


revision = "20261103_0055"
down_revision = "20261028_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    indexes = {index["name"] for index in inspector.get_indexes("users")}

    # Some deployed databases received this column before the Alembic revision
    # was recorded. Treat that schema as already upgraded instead of failing the
    # release with MySQL's duplicate-column error.
    if "auth_provider" not in columns:
        op.add_column("users", sa.Column("auth_provider", sa.String(length=30), nullable=True))
    if "ix_users_auth_provider" not in indexes:
        op.create_index("ix_users_auth_provider", "users", ["auth_provider"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("users")}
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "ix_users_auth_provider" in indexes:
        op.drop_index("ix_users_auth_provider", table_name="users")
    if "auth_provider" in columns:
        op.drop_column("users", "auth_provider")
