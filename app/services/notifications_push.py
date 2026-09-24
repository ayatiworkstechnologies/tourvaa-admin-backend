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
from app.models.notifications import PushSubscription

logger = logging.getLogger(__name__)

# Key under Session.info holding pushes queued in the current transaction.
_PENDING_KEY = "tourvaa_pending_pushes"
# Browsers/push services answer 404/410 when a subscription no longer exists.
_GONE_STATUSES = {404, 410}

DEFAULT_ICON = "/favicon.ico"
PUSH_TTL_SECONDS = 24 * 60 * 60


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


def save_subscription(db: Session, *, endpoint: str, p256dh: str, auth: str, user_id: int | None = None) -> PushSubscription:
    def _update(existing: PushSubscription) -> PushSubscription:
        existing.p256dh = p256dh
        existing.auth = auth
        if user_id:
            existing.user_id = user_id
        db.commit()
        db.refresh(existing)
        return existing

    digest = endpoint_hash(endpoint)
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint_hash == digest).first()
    if existing:
        return _update(existing)

    sub = PushSubscription(endpoint=endpoint, endpoint_hash=digest, p256dh=p256dh, auth=auth, user_id=user_id)
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


def _deliver(db: Session, subs: list[PushSubscription], **message) -> dict:
    sent = failed = 0
    for sub in list(subs):
        result = send_push(sub, **message)
        if result == "sent":
            sent += 1
        else:
            failed += 1
            if result == "gone":
                db.delete(sub)
                subs.remove(sub)  # don't reuse it for this user's next push
    db.commit()
    return {"sent": sent, "failed": failed}


def broadcast_push(db: Session, *, title: str, body: str, url: str = "/", icon: str = DEFAULT_ICON, user_ids: list[int] | None = None) -> dict:
    query = db.query(PushSubscription)
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


def queue_push(db: Session, *, user_id: int | None, title: str, body: str) -> None:
    """Called by enqueue_notification(); sent after the transaction commits."""
    if user_id and is_configured():
        db.info.setdefault(_PENDING_KEY, []).append((user_id, title, body))


def _push_worker(items: list[tuple[int, str, str]]) -> None:
    from app.database import SessionLocal
    from app.models.users import User

    db = SessionLocal()
    try:
        user_ids = {user_id for user_id, _, _ in items}
        subs_by_user: dict[int, list[PushSubscription]] = {}
        for sub in db.query(PushSubscription).filter(PushSubscription.user_id.in_(user_ids)):
            subs_by_user.setdefault(sub.user_id, []).append(sub)
        if not subs_by_user:
            return
        roles = {u.id: (u.role.slug if u.role else "") for u in db.query(User).filter(User.id.in_(subs_by_user))}
        for user_id, title, body in items:
            subs = subs_by_user.get(user_id)
            if subs:
                _deliver(db, subs, title=title, body=body, url=_portal_url(roles.get(user_id, "")))
    except Exception:
        logger.exception("Background web push failed")
    finally:
        db.close()


@event.listens_for(Session, "after_commit")
def _send_pending_pushes(session: Session) -> None:
    items = session.info.pop(_PENDING_KEY, None)
    if items:
        threading.Thread(target=_push_worker, args=(items,), daemon=True, name="web-push").start()


@event.listens_for(Session, "after_rollback")
def _drop_pending_pushes(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
