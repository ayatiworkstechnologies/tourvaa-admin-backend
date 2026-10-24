"""Improve stock email template content and supported call-to-actions.

Revision ID: 20261024_0050
Revises: 20261024_0049
"""

from alembic import op
import sqlalchemy as sa


revision = "20261024_0050"
down_revision = "20261024_0049"
branch_labels = None
depends_on = None


def _replace_stock_template(key: str, old_subject: str, old_body: str, subject: str, body: str) -> None:
    """Upgrade only untouched stock copy; never overwrite administrator edits."""
    templates = sa.table(
        "email_templates",
        sa.column("key", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
    )
    op.execute(
        templates.update()
        .where(templates.c.key == key)
        .where(templates.c.subject == old_subject)
        .where(templates.c.body == old_body)
        .values(subject=subject, body=body)
    )


def upgrade() -> None:
    _replace_stock_template(
        "registration_pending", "Tourvaa registration received",
        "Your Tourvaa registration is received and waiting for admin approval.\n\nName: {{name}}\nEmail: {{email}}\nPhone: {{phone}}\nRequested role: {{role_name}}",
        "New registration pending review - {{role_name}}",
        "A new Tourvaa registration requires review.\n\nName: {{name}}\nEmail: {{email}}\nPhone: {{phone}}\nRequested role: {{role_name}}",
    )
    _replace_stock_template(
        "supplier_approval_pending", "Your Tourvaa supplier profile is pending approval",
        "Hi {{supplier_name}}, your account is active and your supplier profile is pending review. You can sign in to complete your profile and upload verification documents.",
        "Your Tourvaa supplier profile is pending approval",
        "Hi {{supplier_name}}, your supplier profile is awaiting Tourvaa review. Complete any requested profile or verification details in your supplier portal. We will email you when a decision is made.",
    )
    _replace_stock_template(
        "supplier_submitted_verification", "Supplier profile submitted for review",
        "Supplier {{supplier_name}} has submitted their profile for admin review.",
        "Supplier profile submitted for review",
        "Supplier {{supplier_name}} has submitted their profile for admin review. Use the button below to review the supplier profile.",
    )
    _replace_stock_template(
        "agent_submitted_verification", "Agent profile submitted for review",
        "Agent {{agent_name}} has submitted their profile for admin review.",
        "Agent profile submitted for review",
        "Agent {{agent_name}} has submitted their profile for admin review. Use the button below to review the agent profile.",
    )
    _replace_stock_template(
        "booking_declined", "Booking declined - {{booking_code}}",
        "Unfortunately your booking {{booking_code}} for {{tour_name}} was declined by the supplier.\n\nReason: {{reason}}\n\nAny authorized payment has been released. Please browse other available tours or contact our support team.\n\nBrowse tours: {{login_url}}",
        "Booking request could not be confirmed - {{booking_code}}",
        "Unfortunately, your booking request {{booking_code}} for {{tour_name}} could not be confirmed.\n\nReason: {{reason}}\n\nAny authorized payment has been released. Please browse other available tours or contact our support team.\n\nBrowse tours: {{login_url}}",
    )
    _replace_stock_template(
        "payment_received", "Payment received - {{booking_code}}",
        "We have received your payment for booking {{booking_code}}.\n\nTour: {{tour_name}}\nAmount paid: {{currency}} {{amount}}\n\nYou can view your invoice in the customer portal.\n\nView booking: {{login_url}}",
        "Payment received - {{booking_code}}",
        "We have received your payment for booking {{booking_code}}.\n\nTour: {{tour_name}}\nAmount paid: {{currency}} {{amount}}\n\nUse the button below to view your booking and invoice.",
    )
    _replace_stock_template(
        "invoice_generated", "Invoice available - {{invoice_number}}",
        "Hi {{name}}, invoice {{invoice_number}} for booking {{booking_code}} is available. Total: {{currency}} {{total}}. View your booking: {{login_url}}",
        "Invoice available - {{invoice_number}}",
        "Hi {{name}}, invoice {{invoice_number}} for booking {{booking_code}} is available. Total: {{currency}} {{total}}. Use the button below to view your invoice.",
    )
    _replace_stock_template(
        "bank_detail_edit_decision", "Bank-detail edit {{decision}}",
        "Hi {{partner_name}}, your bank-detail edit request was {{decision}}. {{reason}} {{login_url}}",
        "Bank-detail edit {{decision}}",
        "Hi {{partner_name}}, your bank-detail edit request was {{decision}}.\n\n{{reason}}\n\nUse the button below to review your payout settings.",
    )
    _replace_stock_template(
        "contact_enquiry", "New enquiry: {{subject}}",
        "Name: {{name}}\nEmail: {{email}}\nPhone: {{phone}}\nMessage: {{message}}",
        "New enquiry: {{subject}}",
        "Name: {{name}}\nEmail: {{email}}\nPhone: {{phone}}\nAudience: {{audience}}\nEnquiry type: {{enquiry_type}}\nMessage: {{message}}",
    )


def downgrade() -> None:
    # Content changes are intentionally not reversed: administrators may have
    # edited templates after upgrade and their content must be preserved.
    pass
