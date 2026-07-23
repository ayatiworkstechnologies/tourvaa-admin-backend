"""unified registration and account lifecycle

Revision ID: 20260723_0030
Revises: 20260723_0029
"""

from alembic import op
import sqlalchemy as sa

revision = "20260723_0030"
down_revision = "20260723_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "password", existing_type=sa.String(length=255), nullable=True)
    op.add_column("users", sa.Column("user_type", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("country_code", sa.String(length=8), nullable=False, server_default=""))
    op.add_column("users", sa.Column("mobile_number", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("password_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("account_status", sa.String(length=40), nullable=False, server_default="ACTIVE"))
    op.add_column("users", sa.Column("admin_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("admin_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("admin_verified_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivated_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("deactivation_reason", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()))
    op.create_foreign_key("fk_users_admin_verified_by", "users", "users", ["admin_verified_by"], ["id"])
    op.create_foreign_key("fk_users_deactivated_by", "users", "users", ["deactivated_by"], ["id"])
    op.create_index("ix_users_user_type", "users", ["user_type"])
    op.create_index("ix_users_mobile_number", "users", ["mobile_number"], unique=True)
    op.create_index("ix_users_account_status", "users", ["account_status"])
    op.execute("UPDATE users SET email_verified = TRUE WHERE email_verified_at IS NOT NULL")
    op.execute("UPDATE users SET password_created_at = created_at WHERE password IS NOT NULL")
    op.execute("UPDATE users SET admin_verified = TRUE, admin_verified_at = created_at WHERE is_active = TRUE AND approval_status = 'approved'")
    op.execute("UPDATE users SET account_status = CASE WHEN is_active = TRUE AND approval_status = 'approved' THEN 'ACTIVE' WHEN approval_status = 'pending' THEN 'PENDING_ADMIN_VERIFICATION' ELSE 'INACTIVE' END")
    op.execute("UPDATE users SET user_type = CASE WHEN role_id IN (SELECT id FROM roles WHERE slug = 'customer') THEN 'CUSTOMER' WHEN role_id IN (SELECT id FROM roles WHERE slug = 'supplier') THEN 'SUPPLIER' WHEN role_id IN (SELECT id FROM roles WHERE slug = 'agent-reseller') THEN 'AGENT' ELSE 'ADMIN' END")
    op.create_table(
        "user_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_status_history_user_id", "user_status_history", ["user_id"])
    op.create_index("ix_user_status_history_to_status", "user_status_history", ["to_status"])


def downgrade():
    op.drop_table("user_status_history")
    op.drop_index("ix_users_account_status", table_name="users")
    op.drop_index("ix_users_mobile_number", table_name="users")
    op.drop_index("ix_users_user_type", table_name="users")
    op.drop_constraint("fk_users_deactivated_by", "users", type_="foreignkey")
    op.drop_constraint("fk_users_admin_verified_by", "users", type_="foreignkey")
    for column in ["updated_at", "last_login_at", "deactivation_reason", "deactivated_by", "deactivated_at", "admin_verified_by", "admin_verified_at", "admin_verified", "account_status", "password_created_at", "email_verified", "mobile_number", "country_code", "user_type"]:
        op.drop_column("users", column)
    op.alter_column("users", "password", existing_type=sa.String(length=255), nullable=False)
