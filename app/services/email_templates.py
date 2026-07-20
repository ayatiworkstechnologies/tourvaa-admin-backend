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
        "subject": "Verify your Tourvaa email",
        "body": (
            "Hi {{name}}, please verify your email address to complete your account setup. "
            "This link expires in 24 hours.\n\nVerification link: {{verification_url}}"
        ),
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
            "We will notify you as soon as your booking is confirmed by the supplier.\n\n"
            "View your booking: {{login_url}}"
        ),
    },
    {
        "key": "booking_confirmed",
        "name": "Booking Confirmed",
        "subject": "Your booking is confirmed - {{booking_code}}",
        "body": (
            "Great news! Your Tourvaa booking has been confirmed by the supplier.\n\n"
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
        "key": "supplier_submitted_verification",
        "name": "Supplier Submitted Verification",
        "subject": "Supplier profile submitted for review",
        "body": "Supplier {{supplier_name}} has submitted their profile for admin review.",
    },
    {
        "key": "supplier_rejected",
        "name": "Supplier Rejected",
        "subject": "Your Tourvaa supplier profile was rejected",
        "body": "Hi {{supplier_name}}, your supplier profile was rejected. Reason: {{rejection_reason}}",
    },
    {
        "key": "supplier_commission_requested",
        "name": "Supplier Commission Requested",
        "subject": "Supplier commission request pending approval",
        "body": (
            "Supplier {{supplier_name}} requested commission approval.\n\n"
            "Type: {{markup_type}}\n"
            "Value: {{markup_value}}\n\n"
            "Review this request in the admin supplier detail page."
        ),
    },
    {
        "key": "supplier_commission_approved",
        "name": "Supplier Commission Approved",
        "subject": "Your commission request is approved",
        "body": (
            "Hi {{supplier_name}}, your commission request has been approved.\n\n"
            "Type: {{markup_type}}\n"
            "Value: {{markup_value}}\n\n"
            "You can continue using your supplier portal."
        ),
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
        "key": "agent_changes_requested",
        "name": "Agent Changes Requested",
        "subject": "Agent profile changes required",
        "body": "Hi {{agent_name}}, admin requested updates before approval. Required changes: {{pending_requirements}}",
    },
    {
        "key": "agent_approved",
        "name": "Agent Approved",
        "subject": "Your Tourvaa agent profile is approved",
        "body": "Hi {{agent_name}}, your agent profile is approved. You can now manage bookings from the agent portal.",
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
]


def seed_email_templates(db: Session):
    for item in DEFAULT_EMAIL_TEMPLATES:
        template = db.query(EmailTemplate).filter(EmailTemplate.key == item["key"]).first()

        if not template:
            db.add(EmailTemplate(**item, is_active=True))

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
