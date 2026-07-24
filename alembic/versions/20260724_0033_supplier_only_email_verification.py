"""supplier-only email verification

Revision ID: 20260724_0033
Revises: 20260723_0032
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_0033"
down_revision = "20260723_0032"
branch_labels = None
depends_on = None

OLD_SUBJECT = "Verify your Tourvaa email and create your password"
OLD_BODY = (
    "Thanks for registering with Tourvaa.\n\n"
    "Use the secure button below to verify your email and create your password. "
    "After creating your password, your account will be active and you can sign in immediately. "
    "No administrator approval is required.\n\n"
    "For your security, this single-use link expires in 24 hours."
)
NEW_SUBJECT = "Verify your Tourvaa supplier email and create your password"
NEW_BODY = (
    "Thanks for registering as a Tourvaa supplier.\n\n"
    "Use the secure button below to verify your email and create your password. "
    "Your supplier account will then be active and ready to use.\n\n"
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
        .where(email_templates.c.subject == OLD_SUBJECT)
        .where(email_templates.c.body == OLD_BODY)
        .values(subject=NEW_SUBJECT, body=NEW_BODY)
    )

    # Customer and Agent registration no longer requires email verification.
    # Existing compatible accounts already have a password, so activate them.
    op.execute(
        """
        INSERT INTO user_status_history (user_id, from_status, to_status, reason)
        SELECT id, account_status, 'ACTIVE', 'Customer and Agent email verification removed'
        FROM users
        WHERE user_type IN ('CUSTOMER', 'AGENT')
          AND account_status IN ('PENDING_EMAIL_VERIFICATION', 'PENDING_ADMIN_VERIFICATION')
          AND password IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE users
        SET account_status = 'ACTIVE',
            is_active = TRUE,
            approval_status = 'approved',
            password_created_at = COALESCE(password_created_at, created_at),
            email_verification_token = NULL,
            email_verification_expires_at = NULL
        WHERE user_type IN ('CUSTOMER', 'AGENT')
          AND account_status IN ('PENDING_EMAIL_VERIFICATION', 'PENDING_ADMIN_VERIFICATION')
          AND password IS NOT NULL
        """
    )

    # Passwordless registrations started before this release retain their
    # secure setup link, but are no longer represented as awaiting admin review.
    op.execute(
        """
        UPDATE users
        SET account_status = CASE
            WHEN email_verified = TRUE OR email_verified_at IS NOT NULL
                THEN 'PENDING_PASSWORD_CREATION'
            ELSE 'PENDING_EMAIL_VERIFICATION'
        END
        WHERE user_type IN ('CUSTOMER', 'AGENT')
          AND account_status = 'PENDING_ADMIN_VERIFICATION'
          AND password IS NULL
        """
    )

    # Supplier verification remains, but supplier accounts never wait for an
    # administrator after email/password setup.
    op.execute(
        """
        UPDATE users
        SET account_status = CASE
            WHEN (email_verified = TRUE OR email_verified_at IS NOT NULL)
                 AND password_created_at IS NOT NULL
                THEN 'ACTIVE'
            WHEN email_verified = TRUE OR email_verified_at IS NOT NULL
                THEN 'PENDING_PASSWORD_CREATION'
            ELSE 'PENDING_EMAIL_VERIFICATION'
        END,
        is_active = CASE
            WHEN (email_verified = TRUE OR email_verified_at IS NOT NULL)
                 AND password_created_at IS NOT NULL
                THEN TRUE
            ELSE FALSE
        END,
        approval_status = CASE
            WHEN (email_verified = TRUE OR email_verified_at IS NOT NULL)
                 AND password_created_at IS NOT NULL
                THEN 'approved'
            ELSE 'pending'
        END
        WHERE user_type = 'SUPPLIER'
          AND account_status = 'PENDING_ADMIN_VERIFICATION'
        """
    )

    op.execute(
        """
        UPDATE customers
        SET status = 'active'
        WHERE user_id IN (
            SELECT id FROM users
            WHERE user_type = 'CUSTOMER' AND account_status = 'ACTIVE'
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
            WHERE user_type = 'AGENT' AND account_status = 'ACTIVE'
        )
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
                ELSE 'inactive'
            END,
            approval_status = CASE
                WHEN user_id IN (
                    SELECT id FROM users
                    WHERE user_type = 'SUPPLIER' AND account_status = 'ACTIVE'
                ) THEN 'approved'
                ELSE 'email_verification_pending'
            END
        WHERE user_id IN (
            SELECT id FROM users WHERE user_type = 'SUPPLIER'
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
        .where(email_templates.c.subject == NEW_SUBJECT)
        .where(email_templates.c.body == NEW_BODY)
        .values(subject=OLD_SUBJECT, body=OLD_BODY)
    )
