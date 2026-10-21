"""
Centralized helper for all domain event notifications.
Import and call these functions from service layers - keeps notification
logic out of the business logic files.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.services.notifications import enqueue_notification, notify_admins

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)


def send_templated_email(
    db: Session,
    to_email: str | None,
    key: str,
    values: dict,
    fallback_subject: str,
    fallback_html: str,
    *,
    entity_type: str = "email",
    entity_id: int | None = None,
):
    """Render an admin-editable DB email template (falling back to hardcoded HTML) and send it."""
    if not to_email:
        return
    from app.utils.email_templates import render_database_email
    from app.utils.mailer import try_send_email
    try:
        subject, html = render_database_email(db, key, values, fallback_subject, fallback_html)
        try_send_email(
            to_email,
            subject,
            html,
            template_key=key,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except Exception as exc:
        logger.warning("Templated email %s to %s failed: %s", key, to_email, exc)


def admin_notification_recipients(db: Session) -> set[str]:
    """Resolve configured operational admin mailboxes without hardcoding."""
    from app.models.users import User
    from app.models.roles import Role
    admins = db.query(User).join(Role, User.role_id == Role.id).filter(Role.slug.in_(["super-admin", "admin"])).all()
    recipients = {admin.email.strip().lower() for admin in admins if admin.email}
    # System Settings may add operational mailboxes that are not user
    # accounts. BCC is delivered independently so recipient addresses never
    # appear in another recipient's message headers.
    from app.models.settings import SmtpSetting
    setting = db.query(SmtpSetting).first()
    if setting:
        for field in ("admin_notification_to", "admin_notification_cc", "admin_notification_bcc"):
            recipients.update(email.strip().lower() for email in (getattr(setting, field) or "").split(",") if email.strip())
    return recipients


def _do_email_admins(
    db: Session,
    key: str,
    values: dict,
    fallback_subject: str,
    fallback_html: str,
    *,
    entity_type: str = "email",
    entity_id: int | None = None,
) -> None:
    recipients = admin_notification_recipients(db)
    for recipient in recipients:
        send_templated_email(
            db, recipient, key, values, fallback_subject, fallback_html,
            entity_type=entity_type, entity_id=entity_id,
        )


def email_admins(
    db: Session,
    key: str,
    values: dict,
    fallback_subject: str,
    fallback_html: str,
    background_tasks: "BackgroundTasks | None" = None,
    *,
    entity_type: str = "email",
    entity_id: int | None = None,
):
    """Render a DB email template and send it to every super-admin/admin user.

    Runs inline by default, unchanged for existing (low-traffic) callers.
    Pass `background_tasks` from a high-traffic request path (e.g. booking
    creation) to schedule the send instead of blocking the response on SMTP
    - see app.utils.mailer.dispatch_email_task.
    """
    if background_tasks is None:
        _do_email_admins(
            db, key, values, fallback_subject, fallback_html,
            entity_type=entity_type, entity_id=entity_id,
        )
        return
    from app.utils.mailer import dispatch_email_task
    dispatch_email_task(
        background_tasks, db, _do_email_admins, key, values, fallback_subject, fallback_html,
        entity_type=entity_type, entity_id=entity_id,
    )


def _user_email(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    from app.models.users import User
    user = db.query(User).filter(User.id == user_id).first()
    return user.email if user else None


def notify_bank_detail_edit_requested(
    db: Session,
    *,
    partner_type: str,
    partner_id: int,
    partner_name: str,
) -> None:
    """Notify administrators about a protected payout-detail edit request.

    Only the request metadata is delivered. Bank numbers, IBANs, and SWIFT
    codes remain in the authenticated portal and never enter email content.
    """
    from app.config import settings
    from app.utils.email_templates import bank_detail_edit_requested_admin_email

    entity_type = partner_type.lower()
    title = "Bank-detail edit requested"
    notify_admins(
        db,
        notification_type="bank_detail_edit_requested",
        title=title,
        message=f"{partner_type.title()} '{partner_name}' requested a bank-detail edit.",
        entity_type=entity_type,
        entity_id=partner_id,
    )
    admin_url = f"{settings.FRONTEND_URL}/admin/{entity_type}s/{partner_id}"
    email_admins(
        db,
        "bank_detail_edit_requested",
        {
            "partner_type": partner_type.title(),
            "partner_name": partner_name,
            "admin_url": admin_url,
            "button_text": "Review request",
            "button_url": admin_url,
        },
        f"Bank-detail edit request - {partner_name}",
        bank_detail_edit_requested_admin_email(partner_type, partner_name, admin_url),
        entity_type=entity_type,
        entity_id=partner_id,
    )
    db.flush()


# ---------------------------------------------------------------------------
# Supplier events
# ---------------------------------------------------------------------------


def notify_supplier_registered(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_registered", title="New Supplier Registered", message=f"Supplier '{supplier_name}' has registered and is awaiting approval.", entity_type="supplier", entity_id=supplier_id)
    from app.utils.email_templates import supplier_registered_email
    email_admins(
        db,
        "supplier_registered",
        {"supplier_name": supplier_name},
        "New supplier registration awaiting review",
        supplier_registered_email(supplier_name),
    )
    db.flush()


def notify_supplier_submitted_verification(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_submitted_verification", title="Supplier Submitted for Review", message=f"Supplier '{supplier_name}' has submitted their profile for admin review.", entity_type="supplier", entity_id=supplier_id)
    from app.utils.email_templates import supplier_submitted_verification_email
    email_admins(db, "supplier_submitted_verification", {"supplier_name": supplier_name}, "Supplier profile submitted for review", supplier_submitted_verification_email(supplier_name))
    db.flush()


def notify_supplier_approved(
    db: Session,
    *,
    supplier_id: int,
    supplier_name: str,
    user_id: int | None = None,
    background_tasks: "BackgroundTasks | None" = None,
):
    from app.config import settings
    from app.services.notification_delivery import dispatch_lifecycle_email
    notify_admins(db, notification_type="supplier_approved", title="Supplier Approved", message=f"Supplier '{supplier_name}' has been approved.", entity_type="supplier", entity_id=supplier_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_approved", title="Supplier operations unlocked", message=f"Your supplier profile '{supplier_name}' is approved. Tour, booking, calendar and payout features are now available.", entity_type="supplier", entity_id=supplier_id)
        from app.utils.email_templates import approved_email
        login_url = f"{settings.FRONTEND_URL}/supplier-portal/login"
        # Account approval is a lifecycle event: reserve it durably before
        # sending so SMTP failures are visible in notification_deliveries and
        # retried by the lifecycle sweep instead of being silently swallowed.
        dispatch_lifecycle_email(
            db,
            event="supplier_account_approved",
            entity_type="supplier",
            entity_id=supplier_id,
            recipient_type="supplier",
            recipient_email=_user_email(db, user_id),
            template_key="supplier_approved",
            values={"supplier_name": supplier_name, "name": supplier_name, "login_url": login_url},
            fallback_subject="Your Tourvaa supplier operations are unlocked",
            fallback_html=approved_email(supplier_name, login_url),
            background_tasks=background_tasks,
        )
    db.flush()


def notify_supplier_approval_pending(db: Session, *, supplier_id: int, supplier_name: str, user_id: int):
    enqueue_notification(
        db,
        user_id=user_id,
        notification_type="supplier_approval_pending",
        title="Supplier approval pending",
        message="Your account is active. Complete your supplier profile and documents while Tourvaa reviews it.",
        entity_type="supplier",
        entity_id=supplier_id,
    )
    send_templated_email(
        db,
        _user_email(db, user_id),
        "supplier_approval_pending",
        {"supplier_name": supplier_name, "name": supplier_name},
        "Your Tourvaa supplier profile is pending approval",
        "Your account is active and your supplier profile is pending review. Sign in to complete your profile and verification documents.",
    )
    db.flush()


def notify_supplier_account_status(
    db: Session,
    *,
    supplier_id: int,
    supplier_name: str,
    account_status: str,
    reason: str = "",
    user_id: int | None = None,
):
    if not user_id:
        return
    from app.config import settings
    normalized = account_status.upper()
    reactivated = normalized == "ACTIVE"
    title = "Supplier account reactivated" if reactivated else f"Supplier account {normalized.lower()}"
    message = (
        "Your supplier account is active again."
        if reactivated
        else f"Your supplier account is now {normalized.lower()}. {reason}".strip()
    )
    enqueue_notification(
        db,
        user_id=user_id,
        notification_type=f"supplier_account_{normalized.lower()}",
        title=title,
        message=message,
        entity_type="supplier",
        entity_id=supplier_id,
    )
    login_url = f"{settings.FRONTEND_URL}/login"
    template_key = "account_reactivated" if reactivated else "account_deactivated"
    send_templated_email(
        db,
        _user_email(db, user_id),
        template_key,
        {
            "name": supplier_name,
            "supplier_name": supplier_name,
            "reason": reason,
            "login_url": login_url,
        },
        title,
        message,
    )
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


def notify_agent_approved(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None, background_tasks: "BackgroundTasks | None" = None):
    notify_admins(db, notification_type="agent_approved", title="Agent Approved", message=f"Agent '{agent_name}' has been approved.", entity_type="agent", entity_id=agent_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_approved", title="Your agent profile is approved!", message=f"Congratulations! Your agent profile '{agent_name}' has been approved.", entity_type="agent", entity_id=agent_id)
        from app.config import settings
        from app.utils.email_templates import agent_approved_email
        from app.services.notification_delivery import dispatch_lifecycle_email
        login_url = f"{settings.FRONTEND_URL}/agent-portal/login"
        dispatch_lifecycle_email(db, event="agent_account_approved", entity_type="agent", entity_id=agent_id, recipient_type="agent", recipient_email=_user_email(db, user_id), template_key="agent_approved", values={"agent_name": agent_name, "name": agent_name, "login_url": login_url}, fallback_subject="Your Tourvaa agent profile is approved", fallback_html=agent_approved_email(agent_name, login_url), background_tasks=background_tasks)
    db.flush()


def notify_agent_rejected(db: Session, *, agent_id: int, agent_name: str, rejection_reason: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_rejected", title="Agent Profile Rejected", message=f"Your agent profile '{agent_name}' was not approved. Reason: {rejection_reason}", entity_type="agent", entity_id=agent_id)
        from app.utils.email_templates import agent_rejected_email
        send_templated_email(db, _user_email(db, user_id), "agent_rejected", {"agent_name": agent_name, "rejection_reason": rejection_reason}, "Your Tourvaa agent profile was rejected", agent_rejected_email(agent_name, rejection_reason))
    db.flush()


def notify_affiliate_approved(db: Session, *, affiliate_id: int, affiliate_name: str, user_id: int | None = None, background_tasks: "BackgroundTasks | None" = None):
    notify_admins(db, notification_type="affiliate_approved", title="Affiliate Approved", message=f"Affiliate '{affiliate_name}' has been approved.", entity_type="affiliate", entity_id=affiliate_id)
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="affiliate_approved", title="Your affiliate profile is approved!", message=f"Congratulations! Your affiliate profile '{affiliate_name}' has been approved. You can now generate referral links.", entity_type="affiliate", entity_id=affiliate_id)
        from app.config import settings
        from app.utils.email_templates import approved_email
        from app.services.notification_delivery import dispatch_lifecycle_email
        login_url = f"{settings.FRONTEND_URL}/affiliate-portal/login"
        dispatch_lifecycle_email(db, event="affiliate_account_approved", entity_type="affiliate", entity_id=affiliate_id, recipient_type="affiliate", recipient_email=_user_email(db, user_id), template_key="affiliate_approved", values={"affiliate_name": affiliate_name, "name": affiliate_name, "login_url": login_url}, fallback_subject="Your Tourvaa affiliate profile is approved", fallback_html=approved_email(affiliate_name, login_url), background_tasks=background_tasks)
    db.flush()


def notify_affiliate_registered(db: Session, *, affiliate_id: int, affiliate_name: str, background_tasks: "BackgroundTasks | None" = None):
    """Alert Tourvaa operations after a verified affiliate registration."""
    from app.config import settings
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails

    notify_admins(db, notification_type="affiliate_application", title="New Affiliate Application", message=f"{affiliate_name} applied to become an affiliate.", entity_type="affiliate", entity_id=affiliate_id)
    admin_url = f"{settings.FRONTEND_URL}/admin/affiliates/{affiliate_id}"
    dispatch_admin_lifecycle_emails(
        db,
        event="affiliate_registered",
        entity_type="affiliate",
        entity_id=affiliate_id,
        template_key="affiliate_registered",
        values={"affiliate_name": affiliate_name, "admin_url": admin_url},
        fallback_subject=f"New affiliate application - {affiliate_name}",
        fallback_html=f"{affiliate_name} has completed registration and is ready for review. Review it here: {admin_url}",
        background_tasks=background_tasks,
    )
    db.flush()


def notify_affiliate_rejected(db: Session, *, affiliate_id: int, affiliate_name: str, rejection_reason: str = "", user_id: int | None = None, background_tasks: "BackgroundTasks | None" = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="affiliate_rejected", title="Affiliate Application Rejected", message=f"Your affiliate application '{affiliate_name}' was not approved. Reason: {rejection_reason}", entity_type="affiliate", entity_id=affiliate_id)
        from app.config import settings
        from app.services.notification_delivery import dispatch_lifecycle_email
        login_url = f"{settings.FRONTEND_URL}/affiliate-portal/login"
        dispatch_lifecycle_email(db, event="affiliate_account_rejected", entity_type="affiliate", entity_id=affiliate_id, recipient_type="affiliate", recipient_email=_user_email(db, user_id), template_key="affiliate_rejected", values={"affiliate_name": affiliate_name, "name": affiliate_name, "rejection_reason": rejection_reason, "login_url": login_url}, fallback_subject="Your Tourvaa affiliate application needs attention", fallback_html=f"Hi {affiliate_name}, your affiliate application was not approved. Reason: {rejection_reason}", background_tasks=background_tasks)
    db.flush()


def notify_affiliate_activated(db: Session, *, affiliate_id: int, affiliate_name: str, user_id: int | None = None, background_tasks: "BackgroundTasks | None" = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="affiliate_activated", title="Affiliate Account Activated", message=f"Your affiliate account '{affiliate_name}' is active again. Link generation and commissions are unblocked.", entity_type="affiliate", entity_id=affiliate_id)
        from app.config import settings
        from app.services.notification_delivery import dispatch_lifecycle_email
        login_url = f"{settings.FRONTEND_URL}/affiliate-portal/login"
        dispatch_lifecycle_email(db, event="affiliate_account_reactivated", entity_type="affiliate", entity_id=affiliate_id, recipient_type="affiliate", recipient_email=_user_email(db, user_id), template_key="affiliate_reactivated", values={"affiliate_name": affiliate_name, "name": affiliate_name, "login_url": login_url}, fallback_subject="Your Tourvaa affiliate account is active again", fallback_html=f"Hi {affiliate_name}, your affiliate account is active again. Sign in here: {login_url}", background_tasks=background_tasks)
    db.flush()


def notify_affiliate_suspended(db: Session, *, affiliate_id: int, affiliate_name: str, reason: str = "", user_id: int | None = None, background_tasks: "BackgroundTasks | None" = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="affiliate_suspended", title="Affiliate Account Suspended", message=f"Your affiliate account '{affiliate_name}' has been suspended. Reason: {reason}", entity_type="affiliate", entity_id=affiliate_id)
        from app.services.notification_delivery import dispatch_lifecycle_email
        dispatch_lifecycle_email(db, event="affiliate_account_suspended", entity_type="affiliate", entity_id=affiliate_id, recipient_type="affiliate", recipient_email=_user_email(db, user_id), template_key="affiliate_suspended", values={"affiliate_name": affiliate_name, "name": affiliate_name, "reason": reason}, fallback_subject="Your Tourvaa affiliate account has been suspended", fallback_html=f"Hi {affiliate_name}, your affiliate account has been suspended. Reason: {reason}", background_tasks=background_tasks)
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
