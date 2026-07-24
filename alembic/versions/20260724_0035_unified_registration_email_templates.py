"""unified registration lifecycle email templates

Revision ID: 20260724_0035
Revises: 20260724_0034
"""

from alembic import op


revision = "20260724_0035"
down_revision = "20260724_0034"
branch_labels = None
depends_on = None


TEMPLATES = (
    (
        "verification_link_expired",
        "Verification Link Expired",
        "Your Tourvaa verification link expired",
        "Hi {{name}}, your email verification link expired. Request a new link from the Tourvaa registration page.",
    ),
    (
        "supplier_approval_pending",
        "Supplier Approval Pending",
        "Your Tourvaa supplier profile is pending approval",
        "Hi {{supplier_name}}, your account is active and your supplier profile is pending review. You can sign in to complete your profile and upload verification documents.",
    ),
    (
        "supplier_approved",
        "Supplier Approved",
        "Your Tourvaa supplier operations are unlocked",
        "Hi {{supplier_name}}, your supplier profile is approved. Tour management, bookings, calendar and payouts are now available. Sign in here: {{login_url}}",
    ),
    (
        "account_deactivated",
        "Account Deactivated",
        "Your Tourvaa account was deactivated",
        "Hi {{name}}, your Tourvaa account was deactivated. Reason: {{reason}}",
    ),
    (
        "account_reactivated",
        "Account Reactivated",
        "Your Tourvaa account is active again",
        "Hi {{name}}, your Tourvaa account was reactivated. Sign in here: {{login_url}}",
    ),
)


def upgrade():
    op.execute(
        """
        UPDATE email_templates
        SET name = 'Email Verification',
            subject = 'Verify your Tourvaa email and create your password',
            body = 'Hi {{name}}, verify your email and create your password to activate your account. This secure single-use link expires in 24 hours.\n\nVerification link: {{verification_url}}'
        WHERE `key` = 'email_verification'
        """
    )
    for key, name, subject, body in TEMPLATES:
        escaped = tuple(value.replace("'", "''") for value in (key, name, subject, body))
        op.execute(
            f"""
            INSERT INTO email_templates (`key`, name, subject, body, is_active)
            SELECT '{escaped[0]}', '{escaped[1]}', '{escaped[2]}', '{escaped[3]}', TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM email_templates WHERE `key` = '{escaped[0]}'
            )
            """
        )


def downgrade():
    keys = ", ".join(f"'{key}'" for key, *_ in TEMPLATES)
    op.execute(f"DELETE FROM email_templates WHERE `key` IN ({keys})")
