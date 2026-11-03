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
    op.add_column("users", sa.Column("auth_provider", sa.String(length=30), nullable=True))
    op.create_index("ix_users_auth_provider", "users", ["auth_provider"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_auth_provider", table_name="users")
    op.drop_column("users", "auth_provider")
