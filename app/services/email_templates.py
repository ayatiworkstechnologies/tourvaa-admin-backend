import re

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.email_templates import EmailTemplate
from app.schemas.email_templates import EmailTemplateCreate, EmailTemplateUpdate


DEFAULT_EMAIL_TEMPLATES = [
    {
        "key": "registration_pending",
        "name": "Registration Pending",
        "subject": "Tourvaa registration received",
        "body": (
            "Your Tourvaa registration is received and waiting for admin approval.\n\n"
            "Name: {{name}}\n"
            "Email: {{email}}\n"
            "Phone: {{phone}}\n"
            "Requested role: {{role_name}}"
        ),
    },
    {
        "key": "account_approved",
        "name": "Account Approved",
        "subject": "Your Tourvaa account is approved",
        "body": "Hi {{name}}, your Tourvaa account is approved. Login here: {{login_url}}",
    },
    {
        "key": "user_created",
        "name": "User Created",
        "subject": "Your Tourvaa account is ready",
        "body": "Hi {{name}}, an administrator created your Tourvaa account (Email: {{email}}). For security, set your own password using this link before you sign in: {{set_password_url}}",
    },
    {
        "key": "password_reset",
        "name": "Password Reset",
        "subject": "Reset your Tourvaa password",
        "body": "We received a password reset request. Use this secure link within 30 minutes: {{reset_url}}",
    },
    {
        "key": "password_changed",
        "name": "Password Changed",
        "subject": "Your Tourvaa password was changed",
        "body": "Your password was changed successfully. You can now login here: {{login_url}}",
    },
    {
        "key": "email_verification",
        "name": "Email Verification",
        "subject": "Verify your Tourvaa email and create your password",
        "body": (
            "Hi {{name}}, verify your email and create your password to activate your account. "
            "This secure single-use link expires in 24 hours.\n\nVerification link: {{verification_url}}"
        ),
    },
    {
        "key": "otp_login",
        "name": "One-time Login Code",
        "subject": "Your Tourvaa verification code",
        "body": "Hi {{name}}, use this verification code to continue: {{code}}. It expires in 10 minutes. Do not share this code with anyone.",
    },
    {
        "key": "registration_password_created",
        "name": "Registration Password Created",
        "subject": "Your Tourvaa account is ready to sign in",
        "body": (
            "Hi {{name}}, your email has been verified and your password has been created.\n\n"
            "You can now sign in to your {{portal_name}} portal here: {{login_url}}"
        ),
    },
    {
        "key": "verification_link_expired",
        "name": "Verification Link Expired",
        "subject": "Your Tourvaa verification link expired",
        "body": "Hi {{name}}, your email verification link expired. Request a new link from the Tourvaa registration page.",
    },
    {
        "key": "supplier_approval_pending",
        "name": "Supplier Approval Pending",
        "subject": "Your Tourvaa supplier profile is pending approval",
        "body": "Hi {{supplier_name}}, your account is active and your supplier profile is pending review. You can sign in to complete your profile and upload verification documents.",
    },
    {
        "key": "supplier_approved",
        "name": "Supplier Approved",
        "subject": "Your Tourvaa supplier operations are unlocked",
        "body": "Hi {{supplier_name}}, your supplier profile is approved. Tour management, bookings, calendar and payouts are now available. Sign in here: {{login_url}}",
    },
    {
        "key": "account_deactivated",
        "name": "Account Deactivated",
        "subject": "Your Tourvaa account was deactivated",
        "body": "Hi {{name}}, your Tourvaa account was deactivated. Reason: {{reason}}",
    },
    {
        "key": "account_reactivated",
        "name": "Account Reactivated",
        "subject": "Your Tourvaa account is active again",
        "body": "Hi {{name}}, your Tourvaa account was reactivated. Sign in here: {{login_url}}",
    },
    {
        "key": "booking_confirmation",
        "name": "Booking Confirmation",
        "subject": "Booking received - {{booking_code}}",
        "body": (
            "Thank you for booking with Tourvaa! Your booking is received and pending confirmation.\n\n"
            "Booking ID: {{booking_code}}\n"
            "Tour: {{tour_name}}\n"
            "Date: {{tour_date}}\n"
            "Adults: {{adults}}\n"
            "Total: {{currency}} {{total}}\n\n"
            "We will notify you as soon as your booking is confirmed.\n\n"
            "View your booking: {{login_url}}"
        ),
    },
    {
        "key": "booking_confirmed",
        "name": "Booking Confirmed",
        "subject": "Your booking is confirmed - {{booking_code}}",
        "body": (
            "Great news! Your Tourvaa booking is now confirmed.\n\n"
            "Booking ID: {{booking_code}}\n"
            "Tour: {{tour_name}}\n"
            "Date: {{tour_date}}\n"
            "Adults: {{adults}}\n"
            "Total: {{currency}} {{total}}\n\n"
            "Get ready for your trip!\n\nView your booking: {{login_url}}"
        ),
    },
    {
        "key": "booking_cancelled",
        "name": "Booking Cancelled",
        "subject": "Booking cancelled - {{booking_code}}",
        "body": (
            "Your booking {{booking_code}} for {{tour_name}} has been cancelled.\n\n"
            "Reason: {{reason}}\n\n"
            "If you have any questions, please contact our support team.\n\nView your bookings: {{login_url}}"
        ),
    },
    {
        "key": "booking_declined",
        "name": "Booking Declined by Supplier",
        "subject": "Booking declined - {{booking_code}}",
        "body": (
            "Unfortunately your booking {{booking_code}} for {{tour_name}} was declined by the supplier.\n\n"
            "Reason: {{reason}}\n\n"
            "Any authorized payment has been released. Please browse other available tours or contact our support team.\n\nBrowse tours: {{login_url}}"
        ),
    },
    {
        "key": "booking_status_update",
        "name": "Booking Status Update",
        "subject": "Booking update - {{booking_code}}",
        "body": (
            "Your booking {{booking_code}} for {{tour_name}} status has been updated.\n\n"
            "New status: {{new_status}}\n"
            "Reason: {{reason}}\n\n"
            "View your booking: {{login_url}}"
        ),
    },
    {
        "key": "supplier_booking_assigned",
        "name": "Supplier Booking Assigned",
        "subject": "New booking assigned - {{booking_code}}",
        "body": (
            "A new booking has been assigned to you on Tourvaa and is awaiting your acceptance.\n\n"
            "Booking ID: {{booking_code}}\n"
            "Tour: {{tour_name}}\n"
            "Date: {{tour_date}}\n"
            "Customer: {{customer_name}}\n"
            "Adults: {{adults}}\n"
            "Total: {{currency}} {{total}}\n\n"
            "Please log in to your supplier portal to accept or decline this booking.\n\nView booking: {{portal_url}}"
        ),
    },
    {
        "key": "supplier_booking_confirmed",
        "name": "Supplier Booking Confirmed",
        "subject": "Booking confirmed - {{booking_code}}",
        "body": (
            "The booking you accepted is now confirmed.\n\n"
            "Booking ID: {{booking_code}}\n"
            "Tour: {{tour_name}}\n"
            "Date: {{tour_date}}\n"
            "Customer: {{customer_name}}\n"
            "Adults: {{adults}}\n"
            "Total: {{currency}} {{total}}\n\n"
            "Review the booking details and prepare for the tour.\n\nView booking: {{portal_url}}"
        ),
    },
    {
        "key": "supplier_payout_event",
        "name": "Supplier Payout Update",
        "subject": "Payout update - {{payout_code}}",
        "body": (
            "Hi {{supplier_name}},\n\n{{detail}}\n\n"
            "Payout: {{payout_code}}\nAmount: {{currency}} {{amount}}\n"
            "Reference: {{reference_number}}\n\nView your payouts: {{portal_url}}"
        ),
    },

    {
        "key": "admin_booking_event",
        "name": "Admin Booking Event",
        "subject": "{{event_title}} - {{booking_code}}",
        "body": (
            "{{detail}}\n\n"
            "Booking ID: {{booking_code}}\n"
            "Tour: {{tour_name}}\n\n"
            "View booking: {{admin_url}}"
        ),
    },
    {
        "key": "support_message_received",
        "name": "Support Message Received",
        "subject": "New message from {{sender_name}}",
        "body": (
            "A new support message from {{sender_name}} is waiting in your secure Tourvaa portal.\n\n"
            "Open the conversation to read it and reply. For privacy, the message content is not included "
            "in this email. Replies sent directly to this notification email are not added to the conversation."
        ),
    },
    {
        "key": "booking_cancelled_supplier",
        "name": "Booking Cancelled (Supplier)",
        "subject": "Booking cancelled - {{booking_code}}",
        "body": (
            "Booking {{booking_code}} for {{tour_name}} has been cancelled and is no longer on your schedule.\n\n"
            "Reason: {{reason}}\n\n"
            "No further action is needed from you for this booking.\n\nView supplier portal: {{portal_url}}"
        ),
    },
    {
        "key": "refund_processed",
        "name": "Refund Processed",
        "subject": "Refund processed - {{booking_code}}",
        "body": (
            "We have processed a refund for booking {{booking_code}}.\n\n"
            "Tour: {{tour_name}}\n"
            "Refund amount: {{currency}} {{amount}}\n\n"
            "The refund should reflect in your original payment method within a few business days.\n\nView booking: {{login_url}}"
        ),
    },
    {
        "key": "cancellation_requested",
        "name": "Cancellation Requested",
        "subject": "Cancellation request received - {{booking_code}}",
        "body": (
            "We received your cancellation request for booking {{booking_code}} ({{tour_name}}).\n\n"
            "Estimated refund: {{currency}} {{refund_amount}}\n\n"
            "Our team will review this shortly and notify you once it's approved.\n\nView booking: {{login_url}}"
        ),
    },
    {
        "key": "cancellation_approved",
        "name": "Cancellation Approved",
        "subject": "Cancellation approved - {{booking_code}}",
        "body": (
            "Your cancellation request for booking {{booking_code}} ({{tour_name}}) has been approved.\n\n"
            "Refund amount: {{currency}} {{refund_amount}}\n\n"
            "We'll email you again once the refund has been processed.\n\nView booking: {{login_url}}"
        ),
    },
    {
        "key": "cancellation_rejected",
        "name": "Cancellation Rejected",
        "subject": "Cancellation request rejected - {{booking_code}}",
        "body": (
            "Your cancellation request for booking {{booking_code}} ({{tour_name}}) was not approved.\n\n"
            "Reason: {{reason}}\n\n"
            "Your booking remains active. Contact our support team if you have questions.\n\nView booking: {{login_url}}"
        ),
    },
    {
        "key": "booking_reminder",
        "name": "Booking Reminder",
        "subject": "Your tour is coming up - {{booking_code}}",
        "body": "Hi {{name}}, your booking {{booking_code}} for {{tour_name}} is scheduled for {{tour_date}}. Please review your booking details and contact Tourvaa if you need help.\n\nView booking: {{login_url}}",
    },
    {
        "key": "review_request",
        "name": "Review Request",
        "subject": "How was your tour? - {{booking_code}}",
        "body": "Hi {{name}}, your tour {{tour_name}} is complete. We'd love to hear about your experience with booking {{booking_code}}.\n\nLeave a review: {{login_url}}",
    },
    {
        "key": "new_booking_admin",
        "name": "New Booking Created (Admin)",
        "subject": "New booking created - {{booking_code}}",
        "body": (
            "A customer just created a new booking on Tourvaa.\n\n"
            "Booking ID: {{booking_code}}\n"
            "Tour: {{tour_name}}\n"
            "Date: {{tour_date}}\n"
            "Customer: {{customer_name}}\n"
            "Supplier: {{supplier_name}}\n"
            "Adults: {{adults}}\n"
            "Total: {{currency}} {{total}}\n\n"
            "Let the assigned supplier know if they haven't accepted it yet, or reassign the booking from the admin panel.\n\n"
            "View booking: {{admin_url}}"
        ),
    },
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
    {
        "key": "supplier_submitted_verification",
        "name": "Supplier Submitted Verification",
        "subject": "Supplier profile submitted for review",
        "body": "Supplier {{supplier_name}} has submitted their profile for admin review.",
    },
    {
        "key": "supplier_registered",
        "name": "Supplier Registered (Admin)",
        "subject": "New supplier registration awaiting review",
        "body": "Supplier {{supplier_name}} completed registration and is ready for review. Review the supplier in the authenticated admin portal: {{admin_url}}",
    },
    {
        "key": "supplier_rejected",
        "name": "Supplier Rejected",
        "subject": "Your Tourvaa supplier profile was rejected",
        "body": "Hi {{supplier_name}}, your supplier profile was rejected. Reason: {{rejection_reason}}",
    },
    {
        "key": "supplier_changes_requested",
        "name": "Supplier Changes Requested",
        "subject": "Supplier profile changes required",
        "body": "Hi {{supplier_name}}, admin requested updates before approval. Required changes: {{pending_requirements}}",
    },
    {
        "key": "agent_submitted_verification",
        "name": "Agent Submitted Verification",
        "subject": "Agent profile submitted for review",
        "body": "Agent {{agent_name}} has submitted their profile for admin review.",
    },
    {
        "key": "agent_registered",
        "name": "Agent Registered (Admin)",
        "subject": "New agent registration awaiting review",
        "body": "Agent {{agent_name}} completed registration and is ready for review. Review the agent in the authenticated admin portal: {{admin_url}}",
    },
    {
        "key": "agent_changes_requested",
        "name": "Agent Changes Requested",
        "subject": "Agent profile changes required",
        "body": "Hi {{agent_name}}, admin requested updates before approval. Required changes: {{pending_requirements}}",
    },
    {
        "key": "agent_approved",
        "name": "Agent Approved",
        "subject": "Your Tourvaa agent profile is approved",
        "body": "Hi {{agent_name}}, your agent profile is approved. You can now manage bookings from the agent portal: {{login_url}}",
    },
    {
        "key": "affiliate_approved",
        "name": "Affiliate Approved",
        "subject": "Your Tourvaa affiliate profile is approved",
        "body": "Hi {{affiliate_name}}, your affiliate profile is approved. You can now create referral links from the affiliate portal: {{login_url}}",
    },
    {
        "key": "affiliate_registered",
        "name": "Affiliate Registered (Admin)",
        "subject": "New affiliate application - {{affiliate_name}}",
        "body": "{{affiliate_name}} has completed registration and is ready for review. Review the application in the authenticated admin portal: {{admin_url}}",
    },
    {
        "key": "affiliate_rejected",
        "name": "Affiliate Rejected",
        "subject": "Your Tourvaa affiliate application needs attention",
        "body": "Hi {{affiliate_name}}, your affiliate application was not approved. Reason: {{rejection_reason}}. You can review your profile in the affiliate portal: {{login_url}}",
    },
    {
        "key": "affiliate_reactivated",
        "name": "Affiliate Reactivated",
        "subject": "Your Tourvaa affiliate account is active again",
        "body": "Hi {{affiliate_name}}, your affiliate account is active again. You can create referral links and view commissions in the affiliate portal: {{login_url}}",
    },
    {
        "key": "affiliate_suspended",
        "name": "Affiliate Suspended",
        "subject": "Your Tourvaa affiliate account has been suspended",
        "body": "Hi {{affiliate_name}}, your affiliate account has been suspended. Reason: {{reason}}. Contact Tourvaa support if you need help.",
    },
    {
        "key": "agent_rejected",
        "name": "Agent Rejected",
        "subject": "Your Tourvaa agent profile was rejected",
        "body": "Hi {{agent_name}}, your agent profile was rejected. Reason: {{rejection_reason}}",
    },
    {
        "key": "payment_received",
        "name": "Payment Received",
        "subject": "Payment received - {{booking_code}}",
        "body": (
            "We have received your payment for booking {{booking_code}}.\n\n"
            "Tour: {{tour_name}}\n"
            "Amount paid: {{currency}} {{amount}}\n\n"
            "You can view your invoice in the customer portal.\n\nView booking: {{login_url}}"
        ),
    },
    {
        "key": "payment_failed",
        "name": "Payment Failed",
        "subject": "Payment needs attention - {{booking_code}}",
        "body": "Hi {{name}}, we could not complete your payment for {{booking_code}} ({{tour_name}}). {{reason}} You can safely retry from your booking: {{login_url}}",
    },
    {
        "key": "invoice_generated",
        "name": "Invoice Generated",
        "subject": "Invoice available - {{invoice_number}}",
        "body": "Hi {{name}}, invoice {{invoice_number}} for booking {{booking_code}} is available. Total: {{currency}} {{total}}. View your booking: {{login_url}}",
    },
    {
        "key": "tour_submitted",
        "name": "Tour Submitted for Review",
        "subject": "Tour submitted for review - {{tour_name}}",
        "body": "Your tour {{tour_name}} (version {{version}}) has been submitted to Tourvaa for review. {{login_url}}",
    },
    {
        "key": "tour_reviewed",
        "name": "Tour Review Decision",
        "subject": "Tour review update - {{tour_name}}",
        "body": "Your tour {{tour_name}} (version {{version}}) was {{decision}}. {{reason}} {{login_url}}",
    },
]


def seed_email_templates(db: Session):
    for item in DEFAULT_EMAIL_TEMPLATES:
        template = db.query(EmailTemplate).filter(EmailTemplate.key == item["key"]).first()

        if not template:
            db.add(EmailTemplate(**item, is_active=True))
        elif template.key == "booking_confirmed" and template.body:
            # Upgrade only the obsolete supplier-attribution sentence shown
            # in older installations. Do not overwrite any other admin-edited
            # subject/body content when seeding defaults.
            legacy_copy = "Great news! Your Tourvaa booking has been confirmed by the supplier."
            corrected_copy = "Great news! Your Tourvaa booking is now confirmed."
            if legacy_copy in template.body:
                template.body = template.body.replace(legacy_copy, corrected_copy)
        elif template.key == "booking_confirmation" and template.body:
            legacy_confirm_copy = "We will notify you as soon as your booking is confirmed by the supplier."
            corrected_confirm_copy = "We will notify you as soon as your booking is confirmed."
            if legacy_confirm_copy in template.body:
                template.body = template.body.replace(legacy_confirm_copy, corrected_confirm_copy)

    db.commit()


def get_templates(db: Session, page: int | None = None, limit: int | None = None, search: str = ""):
    seed_email_templates(db)
    query = db.query(EmailTemplate)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                EmailTemplate.key.ilike(pattern),
                EmailTemplate.name.ilike(pattern),
                EmailTemplate.subject.ilike(pattern),
            )
        )

    query = query.order_by(EmailTemplate.id.desc())

    if page is None or limit is None:
        return query.all()

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


def get_template(db: Session, template_id: int):
    template = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")

    return template


def create_template(db: Session, data: EmailTemplateCreate):
    existing = db.query(EmailTemplate).filter(EmailTemplate.key == data.key).first()

    if existing:
        raise HTTPException(status_code=400, detail="Template key already exists")

    template = EmailTemplate(**data.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(db: Session, template_id: int, data: EmailTemplateUpdate):
    template = get_template(db, template_id)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template_id: int):
    template = get_template(db, template_id)
    db.delete(template)
    db.commit()
    return True


SAMPLE_VALUES = {
    "name": "Jordan Smith",
    "email": "jordan.smith@example.com",
    "phone": "+1 555 0100",
    "role_name": "Customer",
    "login_url": "https://app.tourvaa.com/login",
    "reset_url": "https://app.tourvaa.com/reset-password?token=sample",
    "set_password_url": "https://app.tourvaa.com/reset-password?token=sample",
    "verification_url": "https://app.tourvaa.com/verify-email?token=sample",
    "portal_name": "supplier",
    "booking_code": "TVA-BKG-000123",
    "tour_name": "Kerala Backwater Escape",
    "tour_date": "2026-08-14",
    "adults": "2",
    "currency": "USD",
    "total": "1,249.00",
    "amount": "1,249.00",
    "reason": "Requested by customer",
    "new_status": "Confirmed",
    "customer_name": "Jordan Smith",
    "supplier_name": "Ayatiworks Technologies",
    "agent_name": "Riverside Travel Partners",
    "portal_url": "https://app.tourvaa.com/admin/bookings/123",
    "admin_url": "https://app.tourvaa.com/admin/bookings/123",
    "event_title": "Supplier accepted booking",
    "detail": "Supplier accepted booking TVA-BKG-000123.",
    "refund_amount": "624.50",
    "markup_type": "percentage",
    "markup_value": "12",
    "pending_requirements": "Updated business license document",
    "rejection_reason": "Incomplete documentation",
}


def preview_template(db: Session, template_id: int) -> dict:
    """Render a template with sample data so admins can preview the outgoing design."""
    from app.utils.email_templates import apply_template_values, base_email

    template = get_template(db, template_id)
    variables = sorted(set(re.findall(r"{{\s*(\w+)\s*}}", f"{template.subject}\n{template.body}")))
    values = {var: SAMPLE_VALUES.get(var, f"Sample {var.replace('_', ' ')}") for var in variables}

    subject = apply_template_values(template.subject, values)
    body = apply_template_values(template.body, values)

    html = base_email(
        subject,
        f"Hi {values.get('name', 'there')},",
        body.replace("\n", "<br />"),
        "View in Tourvaa",
        values.get("login_url", "https://app.tourvaa.com"),
    )

    return {"subject": subject, "html": html, "variables": variables}


def send_test_email(db: Session, template_id: int, to_email: str) -> dict:
    """Send the sample-data preview of a template to a real address for delivery testing."""
    from app.utils.mailer import send_email

    preview = preview_template(db, template_id)
    template = get_template(db, template_id)
    try:
        result = send_email(to_email, preview["subject"], preview["html"], template_key=f"test:{template.key}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Could not send test email: {error}")

    return {"sent": True, "to": to_email, "message_id": result.message_id}
