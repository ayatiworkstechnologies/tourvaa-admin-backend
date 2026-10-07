"""Durable, idempotent lifecycle email delivery.

This service deliberately reuses the project's database email templates and
SMTP mailer.  Domain services reserve a delivery inside their transaction;
the actual SMTP work happens after that transaction and can never roll back a
booking, payment, or cancellation.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.models.notifications import NotificationDelivery
from app.utils.money import utcnow

logger = logging.getLogger(__name__)


def _event_value(event: str | StrEnum) -> str:
    return str(event.value if isinstance(event, StrEnum) else event)


def reserve_delivery(
    db: Session,
    *,
    event: str | StrEnum,
    entity_type: str,
    entity_id: int,
    recipient_type: str,
    recipient_email: str | None,
    template_key: str,
    event_version: str = "1",
) -> NotificationDelivery | None:
    """Reserve exactly one recipient delivery for a business event.

    The unique idempotency key protects against double-clicks, repeated
    webhooks, endpoint retries and duplicate scheduler runs.  A later event
    instance can opt in to a new ``event_version`` without losing that guard.
    """
    email = (recipient_email or "").strip().lower()
    if not email:
        return None
    event_type = _event_value(event)
    key = f"{event_type}:{entity_type}:{entity_id}:{recipient_type}:{email}:{event_version}"
    existing = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == key)
        .first()
    )
    if existing:
        return None
    row = NotificationDelivery(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        recipient_type=recipient_type,
        recipient_email=email,
        template_key=template_key,
        idempotency_key=key,
        status="pending",
    )
    db.add(row)
    db.flush()
    return row


def _deliver(
    db: Session,
    delivery_id: int,
    values: dict,
    fallback_subject: str,
    fallback_html: str,
) -> None:
    """Send one reserved email and record the result without raising."""
    row = db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).first()
    if not row or row.status == "sent":
        return
    row.status = "processing"
    row.attempt_count = (row.attempt_count or 0) + 1
    db.commit()
    try:
        from app.utils.email_templates import render_database_email
        from app.utils.mailer import send_email

        subject, html = render_database_email(
            db, row.template_key, values, fallback_subject, fallback_html
        )
        row.subject = subject
        send_email(
            row.recipient_email,
            subject,
            html,
            template_key=row.template_key,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
        )
        row.status = "sent"
        row.error_message = None
        row.sent_at = utcnow()
    except Exception as error:  # Mail must never break the domain operation.
        row.status = "failed"
        row.error_message = str(error)[:4000]
        logger.warning(
            "Lifecycle email %s for %s/%s to %s failed: %s",
            row.event_type,
            row.entity_type,
            row.entity_id,
            row.recipient_email,
            error,
        )
    finally:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist lifecycle email delivery %s", delivery_id)


def dispatch_lifecycle_email(
    db: Session,
    *,
    event: str | StrEnum,
    entity_type: str,
    entity_id: int,
    recipient_type: str,
    recipient_email: str | None,
    template_key: str,
    values: dict,
    fallback_subject: str,
    fallback_html: str,
    event_version: str = "1",
    background_tasks: BackgroundTasks | None = None,
) -> bool:
    """Reserve and asynchronously deliver a lifecycle email.

    Returns ``False`` for a duplicate or missing recipient.  Email delivery is
    performed through the existing mailer, retaining its SMTP configuration,
    branding, template overrides and EmailLog history.
    """
    row = reserve_delivery(
        db,
        event=event,
        entity_type=entity_type,
        entity_id=entity_id,
        recipient_type=recipient_type,
        recipient_email=recipient_email,
        template_key=template_key,
        event_version=event_version,
    )
    if not row:
        return False

    from app.utils.mailer import dispatch_email_task

    dispatch_email_task(
        background_tasks,
        db,
        _deliver,
        row.id,
        values,
        fallback_subject,
        fallback_html,
    )
    return True


def dispatch_admin_lifecycle_emails(
    db: Session,
    *,
    event: str | StrEnum,
    entity_type: str,
    entity_id: int,
    template_key: str,
    values: dict,
    fallback_subject: str,
    fallback_html: str,
    event_version: str = "1",
    background_tasks: BackgroundTasks | None = None,
) -> int:
    """Deliver an event to every configured Tourvaa operations recipient."""
    from app.utils.notification_triggers import admin_notification_recipients

    delivered = 0
    for recipient in admin_notification_recipients(db):
        delivered += int(
            dispatch_lifecycle_email(
                db,
                event=event,
                entity_type=entity_type,
                entity_id=entity_id,
                recipient_type="tourvaa_admin",
                recipient_email=recipient,
                template_key=template_key,
                values=values,
                fallback_subject=fallback_subject,
                fallback_html=fallback_html,
                event_version=event_version,
                background_tasks=background_tasks,
            )
        )
    return delivered
