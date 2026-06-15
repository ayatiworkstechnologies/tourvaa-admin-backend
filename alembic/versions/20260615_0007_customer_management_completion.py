"""customer management completion

Revision ID: 20260615_0007
Revises: 20260615_0006
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260615_0007"
down_revision = "20260615_0006"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "customers"):
        columns = [
            ("customer_code", sa.Column("customer_code", sa.String(length=30), nullable=True)),
            ("first_name", sa.Column("first_name", sa.String(length=75), nullable=False, server_default="")),
            ("last_name", sa.Column("last_name", sa.String(length=75), nullable=False, server_default="")),
            ("address", sa.Column("address", sa.String(length=255), nullable=False, server_default="")),
            ("profile_image", sa.Column("profile_image", sa.String(length=255), nullable=False, server_default="")),
            ("blocked_reason", sa.Column("blocked_reason", sa.String(length=255), nullable=True)),
            ("blocked_at", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True)),
            ("blocked_by", sa.Column("blocked_by", sa.Integer(), nullable=True)),
        ]

        for name, column in columns:
            if not _has_column(inspector, "customers", name):
                op.add_column("customers", column)

        customers = sa.table(
            "customers",
            sa.column("id", sa.Integer),
            sa.column("customer_code", sa.String),
        )
        rows = bind.execute(sa.select(customers.c.id, customers.c.customer_code)).fetchall()
        for row in rows:
            if not row.customer_code:
                bind.execute(
                    customers.update()
                    .where(customers.c.id == row.id)
                    .values(customer_code=f"TVA-CUS-{row.id:05d}")
                )

        try:
            op.create_index(op.f("ix_customers_customer_code"), "customers", ["customer_code"], unique=True)
        except Exception:
            pass

    if not _has_table(inspector, "customer_communications"):
        op.create_table(
            "customer_communications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("booking_id", sa.Integer(), nullable=True),
            sa.Column("subject", sa.String(length=150), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("sent_by_user_id", sa.Integer(), nullable=True),
            sa.Column("sent_to_email", sa.String(length=150), nullable=False),
            sa.Column("message_type", sa.String(length=30), nullable=False, server_default="admin_message"),
            sa.Column("email_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_customer_communications_id"), "customer_communications", ["id"], unique=False)
        op.create_index(op.f("ix_customer_communications_customer_id"), "customer_communications", ["customer_id"], unique=False)
        op.create_index(op.f("ix_customer_communications_booking_id"), "customer_communications", ["booking_id"], unique=False)
        op.create_index(op.f("ix_customer_communications_sent_by_user_id"), "customer_communications", ["sent_by_user_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "customer_communications"):
        op.drop_index(op.f("ix_customer_communications_sent_by_user_id"), table_name="customer_communications")
        op.drop_index(op.f("ix_customer_communications_booking_id"), table_name="customer_communications")
        op.drop_index(op.f("ix_customer_communications_customer_id"), table_name="customer_communications")
        op.drop_index(op.f("ix_customer_communications_id"), table_name="customer_communications")
        op.drop_table("customer_communications")

    if _has_table(inspector, "customers"):
        try:
            op.drop_index(op.f("ix_customers_customer_code"), table_name="customers")
        except Exception:
            pass

        for column_name in [
            "blocked_by",
            "blocked_at",
            "blocked_reason",
            "profile_image",
            "address",
            "last_name",
            "first_name",
            "customer_code",
        ]:
            if _has_column(inspector, "customers", column_name):
                op.drop_column("customers", column_name)
