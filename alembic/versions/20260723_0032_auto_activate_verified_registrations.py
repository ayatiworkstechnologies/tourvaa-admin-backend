"""auto activate verified registrations

Revision ID: 20260723_0032
Revises: 20260723_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0032"
down_revision = "20260723_0031"
branch_labels = None
depends_on = None

EMAIL_SUBJECT = "Verify your Tourvaa email and create your password"
OLD_EMAIL_BODY = (
    "Thanks for registering with Tourvaa.\n\n"
    "Use the secure button below to verify your email and create your password. "
    "After that, your account will be sent to our team for activation.\n\n"
    "For your security, this single-use link expires in 24 hours."
)
NEW_EMAIL_BODY = (
    "Thanks for registering with Tourvaa.\n\n"
    "Use the secure button below to verify your email and create your password. "
    "After creating your password, your account will be active and you can sign in immediately. "
    "No administrator approval is required.\n\n"
    "For your security, this single-use link expires in 24 hours."
)


def upgrade():
    email_templates = sa.table(
        "email_templates",
        sa.column("key", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
    )
    op.execute(
        email_templates.update()
        .where(email_templates.c.key == "email_verification")
        .where(email_templates.c.subject == EMAIL_SUBJECT)
        .where(email_templates.c.body == OLD_EMAIL_BODY)
        .values(body=NEW_EMAIL_BODY)
    )

    op.execute(
        """
        INSERT INTO user_status_history (user_id, from_status, to_status, reason)
        SELECT id, account_status, 'ACTIVE', 'Admin approval removed; account activated automatically'
        FROM users
        WHERE account_status = 'PENDING_ADMIN_VERIFICATION'
          AND user_type IN ('CUSTOMER', 'AGENT', 'SUPPLIER')
          AND email_verified = TRUE
          AND password_created_at IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE users
        SET account_status = 'ACTIVE',
            is_active = TRUE,
            approval_status = 'approved'
        WHERE account_status = 'PENDING_ADMIN_VERIFICATION'
          AND user_type IN ('CUSTOMER', 'AGENT', 'SUPPLIER')
          AND email_verified = TRUE
          AND password_created_at IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE customers
        SET status = 'active', email_verified = TRUE
        WHERE user_id IN (
            SELECT id FROM users
            WHERE account_status = 'ACTIVE'
              AND user_type = 'CUSTOMER'
              AND email_verified = TRUE
              AND password_created_at IS NOT NULL
        )
        """
    )
    op.execute(
        """
        UPDATE agents
        SET status = 'active',
            approval_status = 'approved',
            approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
            rejection_reason = NULL
        WHERE user_id IN (
            SELECT id FROM users
            WHERE account_status = 'ACTIVE'
              AND user_type = 'AGENT'
              AND email_verified = TRUE
              AND password_created_at IS NOT NULL
        )
        """
    )
    op.execute(
        """
        UPDATE suppliers
        SET status = 'active',
            approval_status = 'approved',
            approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
            rejection_reason = NULL
        WHERE user_id IN (
            SELECT id FROM users
            WHERE account_status = 'ACTIVE'
              AND user_type = 'SUPPLIER'
              AND email_verified = TRUE
              AND password_created_at IS NOT NULL
        )
        """
    )


def downgrade():
    email_templates = sa.table(
        "email_templates",
        sa.column("key", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
    )
    op.execute(
        email_templates.update()
        .where(email_templates.c.key == "email_verification")
        .where(email_templates.c.subject == EMAIL_SUBJECT)
        .where(email_templates.c.body == NEW_EMAIL_BODY)
        .values(body=OLD_EMAIL_BODY)
    )
