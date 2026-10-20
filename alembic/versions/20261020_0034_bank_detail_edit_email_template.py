"""Add the editable admin bank-detail edit request template.

Revision ID: 20261020_0034
Revises: 20261020_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0034"
down_revision = "20261020_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO email_templates (`key`, name, subject, body, is_active) "
            "SELECT :key, :name, :subject, :body, 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM email_templates WHERE `key` = :key)"
        ),
        {
            "key": "bank_detail_edit_requested",
            "name": "Bank-detail Edit Request (Admin)",
            "subject": "Bank-detail edit request - {{partner_name}}",
            "body": (
                "A {{partner_type}} has requested a one-time edit to their payout bank details.\n\n"
                "Account: {{partner_name}}\n\n"
                "For security, no account number, IBAN, or SWIFT/BIC value is included in this email. "
                "Review the request in the authenticated admin portal before enabling the edit.\n\n"
                "Review request: {{admin_url}}"
            ),
        },
    )


def downgrade() -> None:
    op.execute("DELETE FROM email_templates WHERE `key` = 'bank_detail_edit_requested'")
