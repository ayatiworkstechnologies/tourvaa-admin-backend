"""production hardening

Revision ID: 20260615_0001
Revises:
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260615_0001"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    if not _has_table(inspector, table_name):
        return False

    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("slug", sa.String(length=100), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index(op.f("ix_roles_id"), "roles", ["id"], unique=False)
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("slug", sa.String(length=150), nullable=False),
            sa.Column("module", sa.String(length=100), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False, server_default="get"),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index(op.f("ix_permissions_id"), "permissions", ["id"], unique=False)
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=150), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("profile_image", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("address", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("country", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("state", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("city", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("pincode", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("password", sa.String(length=255), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="approved"),
            sa.Column("reset_password_token", sa.String(length=255), nullable=True),
            sa.Column("reset_password_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "role_permissions"):
        op.create_table(
            "role_permissions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("permission_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"]),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_role_permissions_id"), "role_permissions", ["id"], unique=False)
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "app_settings"):
        op.create_table(
            "app_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("label", sa.String(length=150), nullable=False),
            sa.Column("group", sa.String(length=80), nullable=False),
            sa.Column("is_public", sa.Boolean(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )
        op.create_index(op.f("ix_app_settings_id"), "app_settings", ["id"], unique=False)
        op.create_index(op.f("ix_app_settings_key"), "app_settings", ["key"], unique=False)
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "email_templates"):
        op.create_table(
            "email_templates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("subject", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )
        op.create_index(op.f("ix_email_templates_id"), "email_templates", ["id"], unique=False)
        op.create_index(op.f("ix_email_templates_key"), "email_templates", ["key"], unique=False)
        inspector = sa.inspect(bind)

    if _has_table(inspector, "roles") and not _has_column(inspector, "roles", "is_system"):
        op.add_column(
            "roles",
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("roles", "is_system", server_default=None)

    if _has_table(inspector, "permissions") and not _has_column(inspector, "permissions", "is_system"):
        op.add_column(
            "permissions",
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("permissions", "is_system", server_default=None)

    if _has_table(inspector, "users"):
        if not _has_column(inspector, "users", "approval_status"):
            op.add_column(
                "users",
                sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="approved"),
            )
            op.alter_column("users", "approval_status", server_default=None)

        for column_name, length in [
            ("phone", 30),
            ("profile_image", 255),
            ("address", 255),
            ("country", 100),
            ("state", 100),
            ("city", 100),
            ("pincode", 20),
        ]:
            if not _has_column(inspector, "users", column_name):
                op.add_column(
                    "users",
                    sa.Column(column_name, sa.String(length=length), nullable=False, server_default=""),
                )
                op.alter_column("users", column_name, server_default=None)

        if not _has_column(inspector, "users", "reset_password_token"):
            op.add_column("users", sa.Column("reset_password_token", sa.String(length=255), nullable=True))

        if not _has_column(inspector, "users", "reset_password_expires_at"):
            op.add_column("users", sa.Column("reset_password_expires_at", sa.DateTime(timezone=True), nullable=True))

        if not _has_column(inspector, "users", "token_version"):
            op.add_column(
                "users",
                sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            )
            op.alter_column("users", "token_version", server_default=None)

    if _has_table(inspector, "permissions") and not _has_column(inspector, "permissions", "action"):
        op.add_column(
            "permissions",
            sa.Column("action", sa.String(length=20), nullable=False, server_default="get"),
        )
        op.alter_column("permissions", "action", server_default=None)

    if not _has_table(inspector, "audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=100), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("old_values", sa.JSON(), nullable=True),
            sa.Column("new_values", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(length=100), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_audit_logs_id"), "audit_logs", ["id"], unique=False)
        op.create_index(op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False)
        op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
        op.create_index(op.f("ix_audit_logs_entity_type"), "audit_logs", ["entity_type"], unique=False)
        op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "audit_logs"):
        op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
        op.drop_index(op.f("ix_audit_logs_entity_type"), table_name="audit_logs")
        op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
        op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
        op.drop_index(op.f("ix_audit_logs_id"), table_name="audit_logs")
        op.drop_table("audit_logs")

    if _has_column(inspector, "users", "token_version"):
        op.drop_column("users", "token_version")

    if _has_column(inspector, "permissions", "is_system"):
        op.drop_column("permissions", "is_system")

    if _has_column(inspector, "roles", "is_system"):
        op.drop_column("roles", "is_system")
