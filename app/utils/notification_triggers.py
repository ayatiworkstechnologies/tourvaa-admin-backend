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
    recipient_type: str = "user",
    event_version: str = "1",
    background_tasks: "BackgroundTasks | None" = None,
):
    """Reserve an editable templated email in the durable outbox."""
    if not to_email:
        return False
    from app.services.notification_delivery import dispatch_lifecycle_email
    try:
        return dispatch_lifecycle_email(
            db,
            event=key,
            entity_type=entity_type,
            entity_id=entity_id or 0,
            recipient_type=recipient_type,
            recipient_email=to_email,
            template_key=key,
            values=values,
            fallback_subject=fallback_subject,
            fallback_html=fallback_html,
            event_version=event_version,
            background_tasks=background_tasks,
        )
    except Exception as exc:
        logger.warning("Could not reserve templated email %s to %s: %s", key, to_email, exc)
        return False


def admin_notification_recipients(db: Session) -> set[str]:
    """Return only the mailboxes explicitly saved in Admin Settings.

    Being an Admin/Super Admin portal user must not automatically subscribe a
    personal login email to operational lifecycle mail.  Administrators choose
    the recipients in Settings → Admin Notification Recipients instead.
    """
    from app.models.settings import SmtpSetting
    setting = db.query(SmtpSetting).first()
    recipients: set[str] = set()
    if setting:
        # Each address is delivered independently; BCC addresses are never
        # exposed in another recipient's message headers.
        for field in ("admin_notification_to", "admin_notification_cc", "admin_notification_bcc"):
            recipients.update(email.strip().lower() for email in (getattr(setting, field) or "").split(",") if email.strip())
    return recipients


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
    event_version: str = "1",
):
    """Reserve one private, deduplicated outbox delivery per admin recipient."""
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    return dispatch_admin_lifecycle_emails(
        db,
        event=key,
        entity_type=entity_type,
        entity_id=entity_id or 0,
        template_key=key,
        values=values,
        fallback_subject=fallback_subject,
        fallback_html=fallback_html,
        event_version=event_version,
        background_tasks=background_tasks,
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
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
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
    dispatch_admin_lifecycle_emails(
        db,
        event="bank_detail_edit_requested",
        entity_type=entity_type,
        entity_id=partner_id,
        template_key="bank_detail_edit_requested",
        values={
            "partner_type": partner_type.title(),
            "partner_name": partner_name,
            "admin_url": admin_url,
            "button_text": "Review request",
            "button_url": admin_url,
        },
        fallback_subject=f"Bank-detail edit request - {partner_name}",
        fallback_html=bank_detail_edit_requested_admin_email(partner_type, partner_name, admin_url),
    )
    db.flush()


def notify_bank_detail_edit_decision(db: Session, *, partner_type: str, partner_id: int, partner_name: str, user_id: int | None, approved: bool, reason: str = "") -> None:
    """Record the partner-facing outcome without exposing bank data by email."""
    if not user_id:
        return
    from app.config import settings
    from app.services.notification_delivery import dispatch_lifecycle_email
    decision = "approved" if approved else "not approved"
    portal_url = f"{settings.FRONTEND_URL.rstrip('/')}/{partner_type}-portal"
    dispatch_lifecycle_email(
        db, event=f"{partner_type}_bank_edit_{'approved' if approved else 'rejected'}",
        entity_type=partner_type, entity_id=partner_id, recipient_type=partner_type,
        recipient_email=_user_email(db, user_id), template_key="bank_detail_edit_decision",
        values={
            "partner_name": partner_name,
            "decision": decision,
            "reason": reason or "No additional details were provided.",
            "login_url": portal_url,
            "button_text": "Open payout settings",
            "button_url": portal_url,
        },
        fallback_subject=f"Bank-detail edit {decision}",
        fallback_html=f"<p>Hi {partner_name},</p><p>Your bank-detail edit request was {decision}. {reason}</p>",
    )


# ---------------------------------------------------------------------------
# Supplier events
# ---------------------------------------------------------------------------


def notify_supplier_registered(
    db: Session,
    *,
    supplier_id: int,
    supplier_name: str,
    user_id: int | None = None,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Tell Tourvaa operations about a verified supplier registration.

    Registration must not depend on SMTP being available.  Reserve one
    durable delivery per configured admin recipient so failures are visible
    and retryable from the notification-delivery queue.
    """
    from app.config import settings
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    from app.utils.email_templates import supplier_registered_email

    notify_admins(db, notification_type="supplier_registered", title="New Supplier Registered", message=f"Supplier '{supplier_name}' has registered and is awaiting approval.", entity_type="supplier", entity_id=supplier_id)
    admin_url = f"{settings.FRONTEND_URL}/admin/suppliers/{supplier_id}"
    dispatch_admin_lifecycle_emails(
        db,
        event="supplier_registered",
        entity_type="supplier",
        entity_id=supplier_id,
        template_key="supplier_registered",
        values={"supplier_name": supplier_name, "admin_url": admin_url},
        fallback_subject="New supplier registration awaiting review",
        fallback_html=supplier_registered_email(supplier_name),
        background_tasks=background_tasks,
    )
    db.flush()


def notify_supplier_submitted_verification(db: Session, *, supplier_id: int, supplier_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="supplier_submitted_verification", title="Supplier Submitted for Review", message=f"Supplier '{supplier_name}' has submitted their profile for admin review.", entity_type="supplier", entity_id=supplier_id)
    from app.config import settings
    from app.utils.email_templates import supplier_submitted_verification_email
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    dispatch_admin_lifecycle_emails(
        db, event="supplier_submitted_verification", entity_type="supplier", entity_id=supplier_id,
        template_key="supplier_submitted_verification",
        values={
            "supplier_name": supplier_name,
            "admin_url": f"{settings.FRONTEND_URL}/admin/suppliers/{supplier_id}",
            "button_text": "Review supplier profile",
            "button_url": f"{settings.FRONTEND_URL}/admin/suppliers/{supplier_id}",
        },
        fallback_subject="Supplier profile submitted for review",
        fallback_html=supplier_submitted_verification_email(supplier_name),
    )
    if user_id:
        dispatch_lifecycle_email(
            db, event="supplier_verification_received", entity_type="supplier", entity_id=supplier_id,
            recipient_type="supplier", recipient_email=_user_email(db, user_id), template_key="partner_verification_received",
            values={"partner_name": supplier_name, "login_url": f"{settings.FRONTEND_URL}/supplier/profile"},
            fallback_subject="Supplier verification received",
            fallback_html=f"<p>Hi {supplier_name},</p><p>We received your verification information and it is awaiting review.</p>",
        )
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
        entity_type="supplier",
        entity_id=supplier_id,
        recipient_type="supplier",
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
        entity_type="supplier",
        entity_id=supplier_id,
        recipient_type="supplier",
        event_version=normalized,
    )
    db.flush()


def notify_supplier_rejected(db: Session, *, supplier_id: int, supplier_name: str, rejection_reason: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_rejected", title="Supplier Profile Rejected", message=f"Your supplier profile '{supplier_name}' was not approved. Reason: {rejection_reason}", entity_type="supplier", entity_id=supplier_id)
        from app.utils.email_templates import supplier_rejected_email
        from app.services.notification_delivery import dispatch_lifecycle_email
        dispatch_lifecycle_email(
            db, event="supplier_account_rejected", entity_type="supplier", entity_id=supplier_id,
            recipient_type="supplier", recipient_email=_user_email(db, user_id), template_key="supplier_rejected",
            values={"supplier_name": supplier_name, "rejection_reason": rejection_reason},
            fallback_subject="Your Tourvaa supplier profile was rejected",
            fallback_html=supplier_rejected_email(supplier_name, rejection_reason),
        )
    db.flush()


def notify_supplier_reupload_requested(db: Session, *, supplier_id: int, supplier_name: str, requirements: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="supplier_reupload_requested", title="Document Reupload Required", message=f"Please reupload documents for your supplier profile '{supplier_name}'. Required: {requirements}", entity_type="supplier", entity_id=supplier_id)
        from app.config import settings
        from app.utils.email_templates import supplier_changes_requested_email
        login_url = f"{settings.FRONTEND_URL}/supplier/profile"
        from app.services.notification_delivery import dispatch_lifecycle_email
        dispatch_lifecycle_email(
            db, event="supplier_changes_requested", entity_type="supplier", entity_id=supplier_id,
            recipient_type="supplier", recipient_email=_user_email(db, user_id), template_key="supplier_changes_requested",
            values={"supplier_name": supplier_name, "pending_requirements": requirements, "login_url": login_url},
            fallback_subject="Updates required on your supplier profile",
            fallback_html=supplier_changes_requested_email(supplier_name, requirements, login_url),
        )
    db.flush()


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------


def notify_agent_registered(
    db: Session,
    *,
    agent_id: int,
    agent_name: str,
    user_id: int | None = None,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Tell Tourvaa operations about a verified agent registration."""
    from app.config import settings
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    from app.utils.email_templates import agent_submitted_verification_email

    notify_admins(db, notification_type="agent_registered", title="New Agent Registered", message=f"Agent/reseller '{agent_name}' has registered and is awaiting approval.", entity_type="agent", entity_id=agent_id)
    admin_url = f"{settings.FRONTEND_URL}/admin/agents/{agent_id}"
    dispatch_admin_lifecycle_emails(
        db,
        event="agent_registered",
        entity_type="agent",
        entity_id=agent_id,
        template_key="agent_registered",
        values={"agent_name": agent_name, "admin_url": admin_url},
        fallback_subject="New agent registration awaiting review",
        fallback_html=agent_submitted_verification_email(agent_name),
        background_tasks=background_tasks,
    )
    db.flush()


def notify_agent_submitted_verification(db: Session, *, agent_id: int, agent_name: str, user_id: int | None = None):
    notify_admins(db, notification_type="agent_submitted_verification", title="Agent Submitted for Review", message=f"Agent '{agent_name}' has submitted their profile for admin review.", entity_type="agent", entity_id=agent_id)
    from app.config import settings
    from app.utils.email_templates import agent_submitted_verification_email
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    dispatch_admin_lifecycle_emails(
        db, event="agent_submitted_verification", entity_type="agent", entity_id=agent_id,
        template_key="agent_submitted_verification",
        values={
            "agent_name": agent_name,
            "admin_url": f"{settings.FRONTEND_URL}/admin/agents/{agent_id}",
            "button_text": "Review agent profile",
            "button_url": f"{settings.FRONTEND_URL}/admin/agents/{agent_id}",
        },
        fallback_subject="Agent profile submitted for review",
        fallback_html=agent_submitted_verification_email(agent_name),
    )
    if user_id:
        from app.config import settings
        dispatch_lifecycle_email(
            db, event="agent_verification_received", entity_type="agent", entity_id=agent_id,
            recipient_type="agent", recipient_email=_user_email(db, user_id), template_key="partner_verification_received",
            values={"partner_name": agent_name, "login_url": f"{settings.FRONTEND_URL}/agent/profile"},
            fallback_subject="Agent verification received",
            fallback_html=f"<p>Hi {agent_name},</p><p>We received your verification information and it is awaiting review.</p>",
        )
    db.flush()


def notify_agent_changes_requested(db: Session, *, agent_id: int, agent_name: str, requirements: str = "", user_id: int | None = None):
    if user_id:
        enqueue_notification(db, user_id=user_id, notification_type="agent_changes_requested", title="Agent Profile Changes Required", message=f"Please update your agent profile '{agent_name}'. Required: {requirements}", entity_type="agent", entity_id=agent_id)
        from app.config import settings
        from app.utils.email_templates import agent_changes_requested_email
        login_url = f"{settings.FRONTEND_URL}/agent/profile"
        from app.services.notification_delivery import dispatch_lifecycle_email
        dispatch_lifecycle_email(
            db, event="agent_changes_requested", entity_type="agent", entity_id=agent_id,
            recipient_type="agent", recipient_email=_user_email(db, user_id), template_key="agent_changes_requested",
            values={"agent_name": agent_name, "pending_requirements": requirements, "login_url": login_url},
            fallback_subject="Updates required on your agent profile",
            fallback_html=agent_changes_requested_email(agent_name, requirements, login_url),
        )
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
        from app.services.notification_delivery import dispatch_lifecycle_email
        dispatch_lifecycle_email(
            db, event="agent_account_rejected", entity_type="agent", entity_id=agent_id,
            recipient_type="agent", recipient_email=_user_email(db, user_id), template_key="agent_rejected",
            values={"agent_name": agent_name, "rejection_reason": rejection_reason},
            fallback_subject="Your Tourvaa agent profile was rejected",
            fallback_html=agent_rejected_email(agent_name, rejection_reason),
        )
    db.flush()


def notify_agent_commission_requested(
    db: Session,
    *,
    agent_id: int,
    agent_name: str,
    request_type: str,
    request_value: float | int,
    event_version: str,
) -> None:
    """Notify operations that an agent has requested a commission change."""
    from app.config import settings

    request_label = f"{request_value}{'%' if request_type == 'percentage' else ''} {request_type}"
    # In-app notifications use a same-portal route. Email needs the absolute
    # URL below, but an absolute URL is intentionally not navigated by the
    # browser inbox to prevent an open redirect.
    admin_path = f"/admin/agents/{agent_id}"
    admin_url = f"{settings.FRONTEND_URL.rstrip('/')}{admin_path}"
    title = "Agent commission change requested"
    message = f"Agent '{agent_name}' requested a {request_label} commission change."
    notify_admins(
        db,
        notification_type="agent_commission_requested",
        title=title,
        message=message,
        entity_type="agent",
        entity_id=agent_id,
        metadata={"action_url": admin_path, "action_label": "Review request"},
        event_key="agent_commission_requested",
        event_version=event_version,
    )
    email_admins(
        db,
        key="agent_commission_requested",
        values={
            "agent_name": agent_name,
            "request_type": request_type,
            "request_value": request_value,
            "admin_url": admin_url,
            "login_url": admin_url,
        },
        fallback_subject=f"Commission change request - {agent_name}",
        fallback_html=(
            f"<p>Agent <strong>{agent_name}</strong> requested a {request_label} commission change.</p>"
            f"<p><a href=\"{admin_url}\">Review the request</a></p>"
        ),
        entity_type="agent",
        entity_id=agent_id,
        event_version=event_version,
    )
    db.flush()


def notify_agent_commission_decision(
    db: Session,
    *,
    agent_id: int,
    agent_name: str,
    user_id: int | None,
    approved: bool,
    request_type: str,
    request_value: float | int,
    event_version: str,
) -> None:
    """Tell the requesting agent the outcome in-app and by durable email."""
    if not user_id:
        return
    from app.config import settings

    decision = "approved" if approved else "rejected"
    request_label = f"{request_value}{'%' if request_type == 'percentage' else ''} {request_type}"
    portal_url = f"{settings.FRONTEND_URL.rstrip('/')}/agent/profile?tab=commission"
    enqueue_notification(
        db,
        user_id=user_id,
        notification_type=f"agent_commission_{decision}",
        title=f"Commission change request {decision}",
        message=f"Your requested {request_label} commission change was {decision}.",
        entity_type="agent",
        entity_id=agent_id,
        event_key=f"agent_commission_{decision}",
        event_version=event_version,
    )
    send_templated_email(
        db,
        _user_email(db, user_id),
        f"agent_commission_{decision}",
        {
            "agent_name": agent_name,
            "request_type": request_type,
            "request_value": request_value,
            "decision": decision,
            "login_url": portal_url,
        },
        fallback_subject=f"Your commission change request was {decision}",
        fallback_html=(
            f"<p>Hi {agent_name},</p><p>Your requested {request_label} commission change was {decision}.</p>"
            f"<p><a href=\"{portal_url}\">View your commission agreement</a></p>"
        ),
        entity_type="agent",
        entity_id=agent_id,
        recipient_type="agent",
        event_version=event_version,
    )
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


def notify_affiliate_submitted_verification(
    db: Session,
    *,
    affiliate_id: int,
    affiliate_name: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Alert Tourvaa operations when an affiliate submits for review."""
    from app.config import settings
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    from app.utils.email_templates import base_email, esc

    notify_admins(
        db,
        notification_type="affiliate_submitted",
        title="Affiliate Submitted for Review",
        message=f"Affiliate '{affiliate_name}' submitted their profile for review.",
        entity_type="affiliate",
        entity_id=affiliate_id,
    )
    admin_url = f"{settings.FRONTEND_URL}/admin/affiliates/{affiliate_id}"
    dispatch_admin_lifecycle_emails(
        db,
        event="affiliate_submitted_verification",
        entity_type="affiliate",
        entity_id=affiliate_id,
        template_key="affiliate_submitted_verification",
        values={"affiliate_name": affiliate_name, "admin_url": admin_url},
        fallback_subject=f"Affiliate profile submitted for review - {affiliate_name}",
        fallback_html=base_email(
            "Affiliate profile submitted for review",
            f"{affiliate_name} submitted their affiliate profile for review.",
            f"<p><strong>{esc(affiliate_name)}</strong> submitted their affiliate profile for review.</p>",
            "Review affiliate profile",
            admin_url,
        ),
        background_tasks=background_tasks,
    )
    db.flush()


def notify_registration_pending_admin(
    db: Session,
    *,
    user_id: int,
    user_name: str,
    user_email: str,
    role_name: str,
    phone: str = "",
    background_tasks: "BackgroundTasks | None" = None,
):
    """Alert Tourvaa operations that a new registration is pending admin approval."""
    from app.config import settings
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails

    notify_admins(
        db,
        notification_type="registration_pending",
        title="New Registration Pending Approval",
        message=f"New {role_name} registration from {user_name} ({user_email}) is awaiting admin approval.",
        entity_type="user",
        entity_id=user_id,
    )
    admin_url = f"{settings.FRONTEND_URL}/admin/users/{user_id}"
    dispatch_admin_lifecycle_emails(
        db,
        event="registration_pending",
        entity_type="user",
        entity_id=user_id,
        template_key="registration_pending",
        values={
            "name": user_name,
            "email": user_email,
            "phone": phone or "",
            "role_name": role_name,
            "admin_url": admin_url,
            "button_text": "Review registration",
            "button_url": admin_url,
        },
        fallback_subject="Tourvaa registration received",
        fallback_body=(
            f"Your Tourvaa registration is received and waiting for admin approval.\n\n"
            f"Name: {user_name}\nEmail: {user_email}\nPhone: {phone or ''}\nRequested role: {role_name}"
        ),
        background_tasks=background_tasks,
    )
    db.flush()


def notify_payment_pending(
    db: Session,
    *,
    payment_id: int,
    booking_code: str,
    tour_name: str,
    customer_name: str,
    customer_email: str,
    currency: str,
    amount,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify customer that payment is pending (not yet confirmed)."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="payment_pending",
        entity_type="payment",
        entity_id=payment_id,
        recipient_type="customer",
        recipient_email=customer_email,
        template_key="payment_pending",
        values={
            "name": customer_name,
            "booking_code": booking_code,
            "tour_name": tour_name,
            "currency": currency,
            "amount": amount,
            "login_url": login_url,
            "button_text": "View booking",
            "button_url": login_url,
        },
        fallback_subject=f"Payment pending - {booking_code}",
        fallback_html=f"<p>Hi {customer_name}, your payment for booking {booking_code} ({tour_name}) is pending. Amount: {currency} {amount}. We will notify you once the payment is confirmed.</p>",
        background_tasks=background_tasks,
    )


def notify_email_changed(
    db: Session,
    *,
    user_id: int,
    user_name: str,
    old_email: str,
    new_email: str,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Send security notification when a user's email address is changed."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="email_changed",
        entity_type="user",
        entity_id=user_id,
        recipient_type="user",
        recipient_email=new_email,
        template_key="email_changed",
        values={
            "name": user_name,
            "old_email": old_email,
            "new_email": new_email,
            "login_url": login_url,
            "button_text": "View account",
            "button_url": login_url,
        },
        fallback_subject="Your Tourvaa email address was changed",
        fallback_html=f"<p>Hi {user_name}, your Tourvaa account email address was changed from {old_email} to {new_email}. If you did not make this change, please contact Tourvaa support immediately.</p>",
        background_tasks=background_tasks,
    )


def notify_bank_transfer_initiated(
    db: Session,
    *,
    payment_id: int,
    booking_code: str,
    tour_name: str,
    customer_name: str,
    customer_email: str,
    currency: str,
    amount,
    reference_number: str,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify customer that a bank transfer has been initiated."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="bank_transfer_initiated",
        entity_type="payment",
        entity_id=payment_id,
        recipient_type="customer",
        recipient_email=customer_email,
        template_key="bank_transfer_initiated",
        values={
            "name": customer_name,
            "booking_code": booking_code,
            "tour_name": tour_name,
            "currency": currency,
            "amount": amount,
            "reference_number": reference_number,
            "login_url": login_url,
            "button_text": "View booking",
            "button_url": login_url,
        },
        fallback_subject=f"Bank transfer initiated - {booking_code}",
        fallback_html=f"<p>Hi {customer_name}, a bank transfer of {currency} {amount} has been initiated for booking {booking_code} ({tour_name}). Reference: {reference_number}.</p>",
        background_tasks=background_tasks,
    )


def notify_bank_transfer_verified(
    db: Session,
    *,
    payment_id: int,
    booking_code: str,
    tour_name: str,
    customer_name: str,
    customer_email: str,
    currency: str,
    amount,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify customer that a bank transfer has been verified."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="bank_transfer_verified",
        entity_type="payment",
        entity_id=payment_id,
        recipient_type="customer",
        recipient_email=customer_email,
        template_key="bank_transfer_verified",
        values={
            "name": customer_name,
            "booking_code": booking_code,
            "tour_name": tour_name,
            "currency": currency,
            "amount": amount,
            "login_url": login_url,
            "button_text": "View booking",
            "button_url": login_url,
        },
        fallback_subject=f"Bank transfer verified - {booking_code}",
        fallback_html=f"<p>Hi {customer_name}, your bank transfer of {currency} {amount} for booking {booking_code} ({tour_name}) has been verified.</p>",
        background_tasks=background_tasks,
    )


def notify_credit_approval_pending(
    db: Session,
    *,
    payment_id: int,
    booking_code: str,
    tour_name: str,
    customer_name: str,
    customer_email: str,
    currency: str,
    amount,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify customer that credit approval is pending."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="credit_approval_pending",
        entity_type="payment",
        entity_id=payment_id,
        recipient_type="customer",
        recipient_email=customer_email,
        template_key="credit_approval_pending",
        values={
            "name": customer_name,
            "booking_code": booking_code,
            "tour_name": tour_name,
            "currency": currency,
            "amount": amount,
            "login_url": login_url,
            "button_text": "View booking",
            "button_url": login_url,
        },
        fallback_subject=f"Credit approval pending - {booking_code}",
        fallback_html=f"<p>Hi {customer_name}, your credit approval request for booking {booking_code} ({tour_name}) is pending review. Amount: {currency} {amount}.</p>",
        background_tasks=background_tasks,
    )


def notify_credit_approval_approved(
    db: Session,
    *,
    payment_id: int,
    booking_code: str,
    tour_name: str,
    customer_name: str,
    customer_email: str,
    currency: str,
    amount,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify customer that credit approval was approved."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="credit_approval_approved",
        entity_type="payment",
        entity_id=payment_id,
        recipient_type="customer",
        recipient_email=customer_email,
        template_key="credit_approval_approved",
        values={
            "name": customer_name,
            "booking_code": booking_code,
            "tour_name": tour_name,
            "currency": currency,
            "amount": amount,
            "login_url": login_url,
            "button_text": "View booking",
            "button_url": login_url,
        },
        fallback_subject=f"Credit approval approved - {booking_code}",
        fallback_html=f"<p>Hi {customer_name}, your credit approval for booking {booking_code} ({tour_name}) has been approved. Amount: {currency} {amount}.</p>",
        background_tasks=background_tasks,
    )


def notify_credit_approval_rejected(
    db: Session,
    *,
    payment_id: int,
    booking_code: str,
    tour_name: str,
    customer_name: str,
    customer_email: str,
    currency: str,
    amount,
    reason: str,
    login_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify customer that credit approval was rejected."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="credit_approval_rejected",
        entity_type="payment",
        entity_id=payment_id,
        recipient_type="customer",
        recipient_email=customer_email,
        template_key="credit_approval_rejected",
        values={
            "name": customer_name,
            "booking_code": booking_code,
            "tour_name": tour_name,
            "currency": currency,
            "amount": amount,
            "reason": reason,
            "login_url": login_url,
            "button_text": "View booking",
            "button_url": login_url,
        },
        fallback_subject=f"Credit approval rejected - {booking_code}",
        fallback_html=f"<p>Hi {customer_name}, your credit approval request for booking {booking_code} ({tour_name}) was not approved. Reason: {reason}.</p>",
        background_tasks=background_tasks,
    )


def notify_affiliate_payout_completed(
    db: Session,
    *,
    payout_id: int,
    payout_code: str,
    affiliate_id: int,
    affiliate_name: str,
    affiliate_email: str,
    currency: str,
    amount,
    reference_number: str,
    portal_url: str,
    background_tasks: "BackgroundTasks | None" = None,
):
    """Notify affiliate that their payout has been completed."""
    from app.services.notification_delivery import dispatch_lifecycle_email

    dispatch_lifecycle_email(
        db,
        event="affiliate_payout_completed",
        entity_type="affiliate_payout",
        entity_id=payout_id,
        recipient_type="affiliate",
        recipient_email=affiliate_email,
        template_key="affiliate_payout_completed",
        values={
            "affiliate_name": affiliate_name,
            "payout_code": payout_code,
            "currency": currency,
            "amount": amount,
            "reference_number": reference_number,
            "portal_url": portal_url,
            "button_text": "View payouts",
            "button_url": portal_url,
        },
        fallback_subject=f"Affiliate payout completed - {payout_code}",
        fallback_html=f"<p>Hi {affiliate_name}, your affiliate payout {payout_code} for {currency} {amount} has been completed. Reference: {reference_number}.</p>",
        background_tasks=background_tasks,
    )


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
