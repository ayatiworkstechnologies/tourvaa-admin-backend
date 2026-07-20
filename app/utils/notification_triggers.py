"""
Centralized helper for all domain event notifications.
Import and call these functions from service layers - keeps notification
logic out of the business logic files.
"""

import logging

from sqlalchemy.orm import Session

from app.services.notifications import enqueue_notification, notify_admins

logger = logging.getLogger(__name__)


def send_templated_email(db: Session, to_email: str | None, key: str, values: dict, fallback_subject: str, fallback_html: str):
    """Render an admin-editable DB email template (falling back to hardcoded HTML) and send it."""
    if not to_email:
        return
    from app.utils.email_templates import render_database_email
    from app.utils.mailer import try_send_email
    try:
        subject, html = render_database_email(db, key, values, fallback_subject, fallback_html)
        try_send_email(to_email, subject, html)
    except Exception as exc:
        logger.warning("Templated email %s to %s failed: %s", key, to_email, exc)


def email_admins(db: Session, key: str, values: dict, fallback_subject: str, fallback_html: str):
    """Render a DB email template and send it to every super-admin/admin user."""
    from app.models.users import User
    from app.models.roles import Role
    admins = db.query(User).join(Role, User.role_id == Role.id).filter(Role.slug.in_(["super-admin", "admin"])).all()
    for admin in admins:
        send_templated_email(db, admin.email, key, values, fallback_subject, fallback_html)


def _user_email(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    from app.models.users import User
    user = db.query(User).filter(User.id == user_id).first()
    return user.email if user else None


# ---------------------------------------------------------------------------
# Supplier events
# ---------------------------------------------------------------------------


def notify_supplier_registered(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_registered", title="New Supplier Registered", message=f"Supplier '{supplier_name}' has registered and is awaiting approval.", entity_type="supplier", entity_id=supplier_id)
    db.flush()


def notify_supplier_submitted_verification(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_submitted_verification", title="Supplier Submitted for Review", message=f"Supplier '{supplier_name}' has submitted their profile for admin review.", entity_type="supplier", entity_id=supplier_id)
    from app.utils.email_templates import supplier_submitted_verification_email
    email_admins(db, "supplier_submitted_verification", {"supplier_name": supplier_name}, "Supplier profile submitted for review", supplier_submitted_verification_email(supplier_name))
    db.flush()


def notify_supplier_approved(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    from app.config import settings
    notify_admins(db, notification_type="supplier_approved", title="Supplier Approved", message=f"Supplier '{supplier_name}' has been approved.", entity_type="supplier", entity_id=supplier_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_approved", title="Your supplier profile is approved!", message=f"Congratulations! Your supplier profile '{supplier_name}' has been approved. You can now start receiving bookings.", entity_type="supplier", entity_id=supplier_id)
        from app.utils.email_templates import approved_email
        login_url = f"{settings.FRONTEND_URL}/login"
        send_templated_email(db, _user_email(db, user_id), "account_approved", {"name": supplier_name, "login_url": login_url}, "Your Tourvaa account is approved", approved_email(supplier_name, login_url))
    db.flush()


def notify_supplier_rejected(db: Session, *, supplier_id: int, supplier_name: str, rejection_reason: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_rejected", title="Supplier Profile Rejected", message=f"Your supplier profile '{supplier_name}' was not approved. Reason: {rejection_reason}", entity_type="supplier", entity_id=supplier_id)
        from app.utils.email_templates import supplier_rejected_email
        send_templated_email(db, _user_email(db, user_id), "supplier_rejected", {"supplier_name": supplier_name, "rejection_reason": rejection_reason}, "Your Tourvaa supplier profile was rejected", supplier_rejected_email(supplier_name, rejection_reason))
    db.flush()


def notify_supplier_reupload_requested(db: Session, *, supplier_id: int, supplier_name: str, requirements: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_reupload_requested", title="Document Reupload Required", message=f"Please reupload documents for your supplier profile '{supplier_name}'. Required: {requirements}", entity_type="supplier", entity_id=supplier_id)
        from app.config import settings
        from app.utils.email_templates import supplier_changes_requested_email
        login_url = f"{settings.FRONTEND_URL}/supplier/profile"
        send_templated_email(db, _user_email(db, user_id), "supplier_changes_requested", {"supplier_name": supplier_name, "pending_requirements": requirements, "login_url": login_url}, "Updates required on your supplier profile", supplier_changes_requested_email(supplier_name, requirements, login_url))
    db.flush()


def notify_supplier_commission_requested(db: Session, *, supplier_id: int, supplier_name: str, markup_type: str, markup_value: float, user_id: int | None = None):
    notify_admins(
        db,
        notification_type="supplier_commission_requested",
        title="Supplier Commission Request",
        message=f"Supplier '{supplier_name}' requested {markup_value} {markup_type} commission/markup approval.",
        entity_type="supplier",
        entity_id=supplier_id,
    )
    from app.utils.email_templates import supplier_commission_requested_email
    email_admins(db, "supplier_commission_requested", {"supplier_name": supplier_name, "markup_type": markup_type, "markup_value": markup_value}, "Supplier commission request pending approval", supplier_commission_requested_email(supplier_name, markup_type, markup_value))
    if user_id:
        enqueue_notification(
            db,
            user_id=user_id,
            notification_type="supplier_commission_requested",
            title="Commission request submitted",
            message="Your commission request was sent to admin for approval.",
            entity_type="supplier",
            entity_id=supplier_id,
        )
    db.flush()


def notify_supplier_commission_approved(db: Session, *, supplier_id: int, supplier_name: str, markup_type: str, markup_value: float, user_id: int | None = None):
    notify_admins(
        db,
        notification_type="supplier_commission_approved",
        title="Supplier Commission Approved",
        message=f"Commission for supplier '{supplier_name}' approved as {markup_value} {markup_type}.",
        entity_type="supplier",
        entity_id=supplier_id,
    )
    if user_id:
        enqueue_notification(
            db,
            user_id=user_id,
            notification_type="supplier_commission_approved",
            title="Commission request approved",
            message=f"Your commission request was approved as {markup_value} {markup_type}.",
            entity_type="supplier",
            entity_id=supplier_id,
        )
        from app.config import settings
        from app.utils.email_templates import supplier_commission_approved_email
        login_url = f"{settings.FRONTEND_URL}/supplier/profile"
        send_templated_email(db, _user_email(db, user_id), "supplier_commission_approved", {"supplier_name": supplier_name, "markup_type": markup_type, "markup_value": markup_value, "login_url": login_url}, "Your commission request is approved", supplier_commission_approved_email(supplier_name, markup_type, markup_value, login_url))
    db.flush()


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------


def notify_agent_registered(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="agent_registered", title="New Agent Registered", message=f"Agent/reseller '{agent_name}' has registered and is awaiting approval.", entity_type="agent", entity_id=agent_id)
    db.flush()


def notify_agent_submitted_verification(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="agent_submitted_verification", title="Agent Submitted for Review", message=f"Agent '{agent_name}' has submitted their profile for admin review.", entity_type="agent", entity_id=agent_id)
    from app.utils.email_templates import agent_submitted_verification_email
    email_admins(db, "agent_submitted_verification", {"agent_name": agent_name}, "Agent profile submitted for review", agent_submitted_verification_email(agent_name))
    db.flush()


def notify_agent_changes_requested(db: Session, *, agent_id: int, agent_name: str, requirements: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_changes_requested", title="Agent Profile Changes Required", message=f"Please update your agent profile '{agent_name}'. Required: {requirements}", entity_type="agent", entity_id=agent_id)
        from app.config import settings
        from app.utils.email_templates import agent_changes_requested_email
        login_url = f"{settings.FRONTEND_URL}/agent/profile"
        send_templated_email(db, _user_email(db, user_id), "agent_changes_requested", {"agent_name": agent_name, "pending_requirements": requirements, "login_url": login_url}, "Updates required on your agent profile", agent_changes_requested_email(agent_name, requirements, login_url))
    db.flush()


def notify_agent_approved(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="agent_approved", title="Agent Approved", message=f"Agent '{agent_name}' has been approved.", entity_type="agent", entity_id=agent_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_approved", title="Your agent profile is approved!", message=f"Congratulations! Your agent profile '{agent_name}' has been approved.", entity_type="agent", entity_id=agent_id)
        from app.config import settings
        from app.utils.email_templates import agent_approved_email
        login_url = f"{settings.FRONTEND_URL}/login"
        send_templated_email(db, _user_email(db, user_id), "agent_approved", {"agent_name": agent_name, "login_url": login_url}, "Your agent profile is approved", agent_approved_email(agent_name, login_url))
    db.flush()


def notify_agent_rejected(db: Session, *, agent_id: int, agent_name: str, rejection_reason: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_rejected", title="Agent Profile Rejected", message=f"Your agent profile '{agent_name}' was not approved. Reason: {rejection_reason}", entity_type="agent", entity_id=agent_id)
        from app.utils.email_templates import agent_rejected_email
        send_templated_email(db, _user_email(db, user_id), "agent_rejected", {"agent_name": agent_name, "rejection_reason": rejection_reason}, "Your Tourvaa agent profile was rejected", agent_rejected_email(agent_name, rejection_reason))
    db.flush()


# ---------------------------------------------------------------------------
# Booking events
# ---------------------------------------------------------------------------


def notify_booking_status_changed(db: Session, *, booking_id: int, booking_code: str, new_status: str, customer_user_id: int | None = None, supplier_user_id: int | None = None):
    status_messages = {
        "confirmed": "Your booking has been confirmed.",
        "cancelled": "Your booking has been cancelled.",
        "completed": "Your booking has been completed. Thank you!",
        "in_progress": "Your booking is now in progress.",
    }
    msg = status_messages.get(new_status, f"Booking status updated to: {new_status}")
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type=f"booking_{new_status}", title=f"Booking {new_status.capitalize()}", message=f"Booking {booking_code}: {msg}", entity_type="booking", entity_id=booking_id)
    db.flush()


def notify_customer_cancellation_requested(db: Session, *, booking_id: int, booking_code: str, customer_user_id: int | None = None):
    notify_admins(db, notification_type="cancellation_requested", title="Cancellation Requested", message=f"Customer requested cancellation for booking {booking_code}.", entity_type="booking", entity_id=booking_id)
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type="cancellation_requested", title="Cancellation Request Received", message=f"Your cancellation request for booking {booking_code} has been received and is being reviewed.", entity_type="booking", entity_id=booking_id)
    db.flush()


def notify_refund_processed(db: Session, *, booking_id: int, booking_code: str, amount: str, currency: str = "USD", customer_user_id: int | None = None, supplier_user_id: int | None = None):
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type="refund_processed", title="Refund Processed", message=f"A refund of {amount} {currency} has been processed for booking {booking_code}.", entity_type="booking", entity_id=booking_id)
    notify_admins(db, notification_type="refund_processed", title="Refund Processed", message=f"Refund of {amount} {currency} processed for booking {booking_code}.", entity_type="booking", entity_id=booking_id)
    db.flush()


# ---------------------------------------------------------------------------
# Payment events
# ---------------------------------------------------------------------------


def notify_payment_failed(db: Session, *, payment_id: int, booking_code: str, reason: str = "", customer_user_id: int | None = None):
    if customer_user_id:
        enqueue_notification(db, user_id=customer_user_id, notification_type="payment_failed", title="Payment Failed", message=f"Payment for booking {booking_code} failed. {reason}", entity_type="payment", entity_id=payment_id)
    notify_admins(db, notification_type="payment_failed", title="Payment Failed", message=f"Payment for booking {booking_code} failed. {reason}", entity_type="payment", entity_id=payment_id)
    db.flush()
