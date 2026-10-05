"""Add editable booking reminder and review-request email templates.

Revision ID: 20261005_0011
Revises: 20261005_0010
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_0011"
down_revision = "20261005_0010"
branch_labels = None
depends_on = None


def _insert_template(key: str, name: str, subject: str, body: str) -> None:
    # The SELECT guard keeps an administrator's existing template untouched.
    op.get_bind().execute(
        sa.text(
            "INSERT INTO email_templates (`key`, name, subject, body, is_active) "
            "SELECT :key, :name, :subject, :body, 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM email_templates WHERE `key` = :key)"
        ),
        {"key": key, "name": name, "subject": subject, "body": body},
    )


def upgrade():
    _insert_template(
        "booking_reminder",
        "Booking Reminder",
        "Your tour is coming up - {{booking_code}}",
        "Hi {{name}}, your booking {{booking_code}} for {{tour_name}} is scheduled for {{tour_date}}. Please review your booking details and contact Tourvaa if you need help.\\n\\nView booking: {{login_url}}",
    )
    _insert_template(
        "review_request",
        "Review Request",
        "How was your tour? - {{booking_code}}",
        "Hi {{name}}, your tour {{tour_name}} is complete. We'd love to hear about your experience with booking {{booking_code}}.\\n\\nLeave a review: {{login_url}}",
    )


def downgrade():
    op.execute("DELETE FROM email_templates WHERE `key` IN ('booking_reminder', 'review_request')")
