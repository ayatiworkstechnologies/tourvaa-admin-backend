"""Durable, idempotent lifecycle email delivery.

This service deliberately reuses the project's database email templates and
SMTP mailer.  Domain services reserve a delivery inside their transaction;
the actual SMTP work happens after that transaction and can never roll back a
booking, payment, or cancellation.
"""

from __future__ import annotations

import logging
import smtplib
import threading
import uuid
import base64
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from fastapi import BackgroundTasks
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, event as sqlalchemy_event, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notifications import NotificationDelivery
from app.utils.money import utcnow

logger = logging.getLogger(__name__)

MAX_EMAIL_DELIVERY_ATTEMPTS = 3
STALE_PENDING_AFTER = timedelta(minutes=5)
STALE_PROCESSING_AFTER = timedelta(minutes=15)


def _retry_delay(attempt_count: int) -> timedelta:
    """Bounded exponential retry delay: 1, 5, then 25 minutes."""
    return timedelta(minutes=min(60, 5 ** max(0, attempt_count - 1)))


def _event_value(event: str | StrEnum) -> str:
    return str(event.value if isinstance(event, StrEnum) else event)


def _is_permanent_recipient_failure(error: Exception) -> bool:
    """Return true only for SMTP's explicit recipient-rejection responses.

    A rejected mailbox will not become valid because the worker retries it a
    few minutes later.  Keep transient SMTP/auth/network failures retryable,
    but stop retrying explicit recipient failures and expose them for a
    deliberate address correction in Email Logs.
    """
    return isinstance(error, smtplib.SMTPRecipientsRefused)


def _json_safe_payload(value):
    """Convert template data to values accepted by the JSON delivery column.

    Booking and payment models deliberately use Decimal for money.  A durable
    delivery payload is written before the asynchronous email work begins, so
    leaving a Decimal inside it would make SQLAlchemy's JSON serializer fail
    and incorrectly fail the successful payment request.
    """
    return jsonable_encoder(value, custom_encoder={Decimal: str})


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
    try:
        # The database constraint is the final duplicate guard.  The nested
        # transaction keeps a concurrent insert from rolling back the caller's
        # business transaction.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return None
    return row


def _deliver_in_new_session(delivery_id: int) -> None:
    """Deliver a committed outbox row using an isolated worker session."""
    from app.database import SessionLocal

    worker_db = SessionLocal()
    try:
        _deliver(worker_db, delivery_id)
    finally:
        worker_db.close()


def _schedule_after_commit(
    db: Session,
    delivery_id: int,
    background_tasks: BackgroundTasks | None,
) -> None:
    """Start SMTP only after the transaction containing the outbox row commits."""
    state = {"cancelled": False}

    def after_commit(_session: Session) -> None:
        if state["cancelled"]:
            return
        if background_tasks is not None:
            background_tasks.add_task(_deliver_in_new_session, delivery_id)
        else:
            threading.Thread(
                target=_deliver_in_new_session,
                args=(delivery_id,),
                daemon=True,
            ).start()

    def after_rollback(_session: Session) -> None:
        state["cancelled"] = True

    sqlalchemy_event.listen(db, "after_commit", after_commit, once=True)
    sqlalchemy_event.listen(db, "after_rollback", after_rollback, once=True)


def _deliver(
    db: Session,
    delivery_id: int,
) -> None:
    """Send one reserved email and record the result without raising."""
    now = utcnow()
    lease_token = uuid.uuid4().hex
    eligible = or_(
        and_(
            NotificationDelivery.status.in_(("pending", "failed")),
            or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
        ),
        and_(
            NotificationDelivery.status == "processing",
            NotificationDelivery.lease_expires_at.isnot(None),
            NotificationDelivery.lease_expires_at <= now,
        ),
    )
    claimed = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.attempt_count < MAX_EMAIL_DELIVERY_ATTEMPTS,
            eligible,
        )
        .update(
            {
                NotificationDelivery.status: "processing",
                NotificationDelivery.lease_token: lease_token,
                NotificationDelivery.lease_expires_at: now + STALE_PROCESSING_AFTER,
                NotificationDelivery.attempt_count: NotificationDelivery.attempt_count + 1,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if claimed != 1:
        return
    row = db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).first()
    if not row or row.lease_token != lease_token:
        return
    if row.event_type == "email_verification" and row.entity_type == "user":
        from app.models.users import User
        from app.utils.money import as_aware_utc

        user = db.query(User).filter(User.id == row.entity_id).first()
        expires_at = as_aware_utc(user.email_verification_expires_at) if user and user.email_verification_expires_at else None
        current_token = user.email_verification_token if user else None
        event_version = row.idempotency_key.rsplit(":", 1)[-1]
        if not user or not current_token or current_token != event_version or not expires_at or expires_at <= utcnow():
            row.status = "exhausted"
            row.exhausted_at = utcnow()
            row.error_message = "Verification link expired or was superseded; delivery was not sent."
            row.lease_token = None
            row.lease_expires_at = None
            db.commit()
            return
    if row.event_type in {"otp_login", "password_reset"} and row.entity_type == "user":
        from app.models.users import User
        from app.utils.money import as_aware_utc

        user = db.query(User).filter(User.id == row.entity_id).first()
        event_version = row.idempotency_key.rsplit(":", 1)[-1]
        if row.event_type == "otp_login":
            current_token = user.otp_code_hash if user else None
            expires_at = as_aware_utc(user.otp_expires_at) if user and user.otp_expires_at else None
        else:
            current_token = user.reset_password_token if user else None
            expires_at = as_aware_utc(user.reset_password_expires_at) if user and user.reset_password_expires_at else None
        if not user or current_token != event_version or not expires_at or expires_at <= utcnow():
            row.status = "exhausted"
            row.exhausted_at = utcnow()
            row.error_message = "Security token expired or was superseded; delivery was not sent."
            row.lease_token = None
            row.lease_expires_at = None
            db.commit()
            return
    payload = row.payload_json or {}
    values = payload.get("values") or {}
    fallback_subject = payload.get("fallback_subject")
    fallback_html = payload.get("fallback_html")
    if not fallback_subject or not fallback_html:
        row.status = "manual_review"
        row.error_message = "Delivery payload is unavailable; automatic replay is unsafe."
        row.lease_token = None
        row.lease_expires_at = None
        db.commit()
        return
    try:
        from app.utils.email_templates import render_database_email
        from app.utils.mailer import send_email

        subject, html = render_database_email(
            db, row.template_key, values, fallback_subject, fallback_html
        )
        row.subject = subject
        attachments = [
            (item["name"], base64.b64decode(item["content_b64"]), item.get("kind", "bin"))
            for item in payload.get("attachments", [])
        ]
        result = send_email(
            row.recipient_email,
            subject,
            html,
            attachments,
            template_key=row.template_key,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
        )
        if not result.ok:
            raise RuntimeError(result.error or "SMTP delivery failed")
        accepted_at = utcnow()
        updated = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.status == "processing",
                NotificationDelivery.lease_token == lease_token,
            )
            .update(
                {
                    NotificationDelivery.status: "smtp_accepted",
                    NotificationDelivery.subject: subject,
                    NotificationDelivery.error_message: None,
                    NotificationDelivery.sent_at: accepted_at,
                    NotificationDelivery.smtp_accepted_at: accepted_at,
                    NotificationDelivery.next_attempt_at: None,
                    NotificationDelivery.lease_token: None,
                    NotificationDelivery.lease_expires_at: None,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            logger.error("SMTP accepted lifecycle email %s but worker ownership was lost; delivery state is uncertain", delivery_id)
            return
        try:
            db.commit()
        except Exception:
            db.rollback()
            # SMTP has no transactional handshake with our database. Leaving
            # the lease to expire permits recovery but can produce a duplicate;
            # the uncertainty is explicit in logs and monitoring.
            logger.exception("SMTP accepted lifecycle email %s but its database acknowledgement failed; duplicate delivery is possible", delivery_id)
        return
    except Exception as error:  # Mail must never break the domain operation.
        db.rollback()
        attempt_count = row.attempt_count or 1
        exhausted = attempt_count >= MAX_EMAIL_DELIVERY_ATTEMPTS or _is_permanent_recipient_failure(error)
        failure_values = {
            NotificationDelivery.status: "exhausted" if exhausted else "failed",
            NotificationDelivery.error_message: str(error)[:4000],
            NotificationDelivery.next_attempt_at: None if exhausted else utcnow() + _retry_delay(attempt_count),
            NotificationDelivery.exhausted_at: utcnow() if exhausted else None,
            NotificationDelivery.lease_token: None,
            NotificationDelivery.lease_expires_at: None,
        }
        db.query(NotificationDelivery).filter(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.lease_token == lease_token,
        ).update(failure_values, synchronize_session=False)
        logger.warning(
            "Lifecycle email %s for %s/%s to %s failed: %s",
            row.event_type,
            row.entity_type,
            row.entity_id,
            row.recipient_email,
            error,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not persist lifecycle email failure %s", delivery_id)


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
    attachments: list[tuple[str, bytes, str]] | None = None,
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

    row.payload_json = _json_safe_payload({
        "values": values,
        "fallback_subject": fallback_subject,
        "fallback_html": fallback_html,
        "attachments": [
            {"name": name, "content_b64": base64.b64encode(content).decode("ascii"), "kind": kind}
            for name, content, kind in (attachments or [])
        ],
    })

    _schedule_after_commit(db, row.id, background_tasks)
    return True


def retry_failed_lifecycle_emails(db: Session) -> int:
    """Recover failed and stale lifecycle emails up to the finite limit.

    This is deliberately best-effort: a delivery failure is recorded and never
    changes a booking, payment, cancellation, or payout state.
    """
    now = utcnow()
    pending_cutoff = now - STALE_PENDING_AFTER
    processing_cutoff = now - STALE_PROCESSING_AFTER
    rows = (
        db.query(NotificationDelivery)
        .filter(
            or_(
                and_(
                    NotificationDelivery.status == "failed",
                    or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
                ),
                and_(
                    NotificationDelivery.status == "pending",
                    NotificationDelivery.updated_at < pending_cutoff,
                ),
                and_(
                    NotificationDelivery.status == "processing",
                    or_(NotificationDelivery.lease_expires_at <= now, NotificationDelivery.updated_at < processing_cutoff),
                ),
            ),
            NotificationDelivery.attempt_count < MAX_EMAIL_DELIVERY_ATTEMPTS,
        )
        .order_by(NotificationDelivery.updated_at.asc())
        .limit(100)
        .all()
    )
    retried = 0
    for row in rows:
        payload = row.payload_json or {}
        if not payload.get("fallback_subject") or not payload.get("fallback_html"):
            row.status = "manual_review"
            row.error_message = "Delivery payload is unavailable; automatic replay is unsafe."
            db.commit()
            continue
        _deliver(db, row.id)
        retried += 1
    return retried


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
