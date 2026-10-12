"""Browser web push (VAPID) for Tourvaa notifications.

Every in-app notification created through enqueue_notification() is also
pushed to the recipient's subscribed browsers - but only after the caller's
transaction commits (a rolled-back booking never pushes), and from a
background thread so a slow push service never delays the request.
"""
import hashlib
import json
import logging
import threading
from pathlib import Path

from pywebpush import WebPushException, webpush
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.notifications import Notification, PushDeliveryLog, PushSubscription
from app.utils.money import utcnow

logger = logging.getLogger(__name__)

# Key under Session.info holding pushes queued in the current transaction.
_PENDING_KEY = "tourvaa_pending_pushes"
# Browsers/push services answer 404/410 when a subscription no longer exists.
_GONE_STATUSES = {404, 410}

DEFAULT_ICON = "/favicon.ico"
PUSH_TTL_SECONDS = 24 * 60 * 60
MAX_PUSH_DELIVERY_ATTEMPTS = 3


def _vapid_private_key() -> str | None:
    """Inline VAPID_PRIVATE_KEY wins; otherwise the PEM file, resolved
    relative to the backend root (the folder holding app/)."""
    if settings.VAPID_PRIVATE_KEY.strip():
        return settings.VAPID_PRIVATE_KEY.strip()
    path = Path(settings.VAPID_PRIVATE_KEY_FILE)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return str(path) if path.is_file() else None


def is_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and _vapid_private_key())


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def save_subscription(db: Session, *, endpoint: str, p256dh: str, auth: str, user_id: int | None = None, platform: str | None = None, device_type: str | None = None) -> PushSubscription:
    def _update(existing: PushSubscription) -> PushSubscription:
        existing.p256dh = p256dh
        existing.auth = auth
        existing.platform = platform or existing.platform
        existing.device_type = device_type or existing.device_type
        existing.is_active = 1
        existing.last_used_at = utcnow()
        if user_id:
            existing.user_id = user_id
        db.commit()
        db.refresh(existing)
        return existing

    digest = endpoint_hash(endpoint)
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint_hash == digest).first()
    if existing:
        return _update(existing)

    sub = PushSubscription(endpoint=endpoint, endpoint_hash=digest, p256dh=p256dh, auth=auth, user_id=user_id, platform=platform, device_type=device_type, is_active=1, last_used_at=utcnow())
    db.add(sub)
    try:
        db.commit()
    except IntegrityError:
        # Two tabs/requests saved the same browser at once - update instead.
        db.rollback()
        return _update(db.query(PushSubscription).filter(PushSubscription.endpoint_hash == digest).one())
    db.refresh(sub)
    return sub


def delete_subscription(db: Session, endpoint: str, user_id: int | None = None) -> None:
    query = db.query(PushSubscription).filter(PushSubscription.endpoint_hash == endpoint_hash(endpoint))
    if user_id is not None:
        query = query.filter(PushSubscription.user_id == user_id)
    query.delete()
    db.commit()


def send_push(sub: PushSubscription, *, title: str, body: str, url: str = "/", icon: str = DEFAULT_ICON, action: str | None = None, phone: str | None = None, wa_msg: str | None = None) -> str:
    """Returns "sent", "gone" (subscription expired - safe to delete) or
    "failed" (anything else, incl. missing server config - keep it)."""
    private_key = _vapid_private_key()
    if not settings.VAPID_PUBLIC_KEY or not private_key:
        logger.warning("Web push skipped: VAPID keys are not configured")
        return "failed"

    payload = {"title": title, "body": body, "url": url, "icon": icon}
    if action:
        payload["action"] = action
    if phone:
        payload["phone"] = phone
    if wa_msg:
        payload["waMsg"] = wa_msg

    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims={"sub": settings.VAPID_MAILTO},
            # How long the push service keeps the message for an offline
            # device. pywebpush's default of 0 means "drop unless online right
            # now"; Windows/Edge rejects it outright (400) and Chrome/Firefox
            # silently lose pushes for sleeping laptops and phones.
            ttl=PUSH_TTL_SECONDS,
            timeout=10,
        )
        return "sent"
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in _GONE_STATUSES:
            return "gone"
        logger.warning("Web push failed (HTTP %s) for subscription %s", status, sub.id)
        return "failed"
    except Exception:  # bad key, network error ... never break the caller
        logger.exception("Web push error for subscription %s", sub.id)
        return "failed"


def _deliver(db: Session, subs: list[PushSubscription], notification_id: int | None = None, event_key: str | None = None, recipient_user_id: int | None = None, **message) -> dict:
    sent = failed = 0
    for sub in list(subs):
        log = PushDeliveryLog(notification_id=notification_id, subscription_id=sub.id, event_key=event_key, recipient_user_id=recipient_user_id or sub.user_id, status="processing", attempt_count=1)
        db.add(log)
        result = send_push(sub, **message)
        if result == "sent":
            sent += 1
            log.status = "sent"
            log.sent_at = utcnow()
            sub.last_used_at = utcnow()
        else:
            failed += 1
            log.status = "invalid_token" if result == "gone" else "failed"
            log.failed_at = utcnow()
            log.error_message = "Subscription expired" if result == "gone" else "Web push delivery failed"
            if result == "gone":
                sub.is_active = 0
                subs.remove(sub)  # don't reuse it for this user's next push
    db.commit()
    return {"sent": sent, "failed": failed}


def broadcast_push(db: Session, *, title: str, body: str, url: str = "/", icon: str = DEFAULT_ICON, user_ids: list[int] | None = None) -> dict:
    query = db.query(PushSubscription).filter(PushSubscription.is_active == 1)
    if user_ids:
        query = query.filter(PushSubscription.user_id.in_(user_ids))
    return _deliver(db, query.all(), title=title, body=body, url=url, icon=icon)


# --- automatic push for in-app notifications ---------------------------------

def _portal_url(role_slug: str) -> str:
    slug = (role_slug or "").lower()
    if "supplier" in slug:
        return "/supplier/notifications"
    if "agent" in slug or "reseller" in slug:
        return "/agent/dashboard"
    if "affiliate" in slug:
        return "/affiliate/dashboard"
    if "customer" in slug:
        return "/customer/dashboard"
    return "/admin/notifications"


def queue_push(db: Session, *, notification_id: int | None, user_id: int | None, title: str, body: str, url: str = "/") -> None:
    """Called by enqueue_notification(); sent after the transaction commits."""
    if user_id and is_configured():
        db.info.setdefault(_PENDING_KEY, []).append((notification_id, user_id, title, body, url))


def _push_worker(items: list[tuple[int | None, int, str, str, str]]) -> None:
    from app.database import SessionLocal
    from app.models.users import User

    db = SessionLocal()
    try:
        user_ids = {user_id for _, user_id, _, _, _ in items}
        subs_by_user: dict[int, list[PushSubscription]] = {}
        for sub in db.query(PushSubscription).filter(PushSubscription.user_id.in_(user_ids), PushSubscription.is_active == 1):
            subs_by_user.setdefault(sub.user_id, []).append(sub)
        if not subs_by_user:
            return
        roles = {u.id: (u.role.slug if u.role else "") for u in db.query(User).filter(User.id.in_(subs_by_user))}
        notifications = {n.id: n for n in db.query(Notification).filter(Notification.id.in_([notification_id for notification_id, *_ in items if notification_id])).all()}
        for notification_id, user_id, title, body, url in items:
            subs = subs_by_user.get(user_id)
            if subs:
                row = notifications.get(notification_id)
                _deliver(db, subs, notification_id=notification_id, event_key=row.event_key if row else None, recipient_user_id=user_id, title=title, body=body, url=url or _portal_url(roles.get(user_id, "")))
    except Exception:
        logger.exception("Background web push failed")
    finally:
        db.close()


def retry_failed_push_deliveries(db: Session) -> dict:
    """Retry transient browser-push failures using the original notification.

    A delivery row is updated in place: this preserves a real per-device audit
    trail and gives a finite attempt count even when workers restart.
    """
    rows = (
        db.query(PushDeliveryLog)
        .filter(PushDeliveryLog.status == "failed", PushDeliveryLog.attempt_count < MAX_PUSH_DELIVERY_ATTEMPTS)
        .order_by(PushDeliveryLog.id.asc())
        .limit(100)
        .all()
    )
    sent = failed = skipped = 0
    for row in rows:
        sub = db.query(PushSubscription).filter(PushSubscription.id == row.subscription_id).first()
        notification = db.query(Notification).filter(Notification.id == row.notification_id).first()
        if not sub or not sub.is_active or not notification:
            row.status = "skipped"
            row.error_message = "Subscription or notification is no longer available"
            skipped += 1
            continue
        metadata = notification.metadata_json or {}
        result = send_push(sub, title=notification.title, body=notification.message, url=metadata.get("action_url") or "/")
        row.attempt_count += 1
        if result == "sent":
            row.status = "sent"
            row.error_message = None
            row.sent_at = utcnow()
            sub.last_used_at = utcnow()
            sent += 1
        elif result == "gone":
            row.status = "invalid_token"
            row.error_message = "Subscription expired"
            row.failed_at = utcnow()
            sub.is_active = 0
            failed += 1
        else:
            row.status = "failed"
            row.error_message = "Web push delivery failed"
            row.failed_at = utcnow()
            failed += 1
    db.commit()
    return {"retried": len(rows), "sent": sent, "failed": failed, "skipped": skipped}


@event.listens_for(Session, "after_commit")
def _send_pending_pushes(session: Session) -> None:
    items = session.info.pop(_PENDING_KEY, None)
    if items:
        threading.Thread(target=_push_worker, args=(items,), daemon=True, name="web-push").start()


@event.listens_for(Session, "after_rollback")
def _drop_pending_pushes(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
