"""unified registration and independent supplier approval

Revision ID: 20260724_0034
Revises: 20260724_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_0034"
down_revision = "20260724_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "users",
        "approval_status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.create_table(
        "supplier_approval_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_approval_history_id", "supplier_approval_history", ["id"])
    op.create_index("ix_supplier_approval_history_supplier_id", "supplier_approval_history", ["supplier_id"])
    op.create_index("ix_supplier_approval_history_to_status", "supplier_approval_history", ["to_status"])
    op.create_index("ix_supplier_approval_history_changed_by", "supplier_approval_history", ["changed_by"])

    # Preserve access for existing customer/agent accounts created by the
    # immediately preceding release while normalizing the independent status.
    op.execute(
        """
        UPDATE users
        SET approval_status = 'NOT_REQUIRED',
            email_verified = TRUE,
            email_verified_at = COALESCE(email_verified_at, created_at)
        WHERE user_type IN ('CUSTOMER', 'AGENT')
          AND account_status = 'ACTIVE'
          AND password IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE customers
        SET email_verified = TRUE
        WHERE user_id IN (
            SELECT id FROM users
            WHERE user_type = 'CUSTOMER' AND account_status = 'ACTIVE'
        )
        """
    )
    op.execute(
        """
        UPDATE agents
        SET approval_status = 'NOT_REQUIRED'
        WHERE user_id IN (
            SELECT id FROM users
            WHERE user_type = 'AGENT'
        )
        """
    )

    # Supplier login state stays independent from operational approval.
    op.execute(
        """
        UPDATE suppliers
        SET approval_status = CASE
            WHEN UPPER(approval_status) IN ('APPROVED', 'APPROVED_LIVE') THEN 'APPROVED'
            WHEN UPPER(approval_status) IN ('PARTIAL_APPROVED', 'MORE_INFORMATION_REQUIRED') THEN 'MORE_INFORMATION_REQUIRED'
            ELSE 'PENDING'
        END
        """
    )
    op.execute(
        """
        UPDATE users
        SET approval_status = (
                SELECT suppliers.approval_status
                FROM suppliers
                WHERE suppliers.user_id = users.id
            ),
            account_status = CASE
                WHEN (email_verified = TRUE OR email_verified_at IS NOT NULL)
                     AND password IS NOT NULL THEN 'ACTIVE'
                ELSE account_status
            END,
            is_active = CASE
                WHEN (email_verified = TRUE OR email_verified_at IS NOT NULL)
                     AND password IS NOT NULL THEN TRUE
                ELSE is_active
            END
        WHERE user_type = 'SUPPLIER'
          AND EXISTS (SELECT 1 FROM suppliers WHERE suppliers.user_id = users.id)
        """
    )
    op.execute(
        """
        UPDATE suppliers
        SET status = CASE
            WHEN user_id IN (
                SELECT id FROM users
                WHERE user_type = 'SUPPLIER' AND account_status = 'ACTIVE'
            ) THEN 'active'
            ELSE status
        END
        """
    )
    op.execute(
        """
        INSERT INTO supplier_approval_history (supplier_id, from_status, to_status, notes)
        SELECT id, NULL, approval_status, 'Status normalized by unified registration migration'
        FROM suppliers
        """
    )


def downgrade():
    op.drop_index("ix_supplier_approval_history_changed_by", table_name="supplier_approval_history")
    op.drop_index("ix_supplier_approval_history_to_status", table_name="supplier_approval_history")
    op.drop_index("ix_supplier_approval_history_supplier_id", table_name="supplier_approval_history")
    op.drop_index("ix_supplier_approval_history_id", table_name="supplier_approval_history")
    op.drop_table("supplier_approval_history")
    op.alter_column(
        "users",
        "approval_status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
