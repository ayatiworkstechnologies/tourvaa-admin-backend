from math import ceil
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.utils.money import utcnow
from app.models.notifications import Notification, NotificationLog
from app.schemas.notifications import NotificationCreate
from app.models.users import User


# These are immutable lifecycle events.  They are often emitted from a webhook
# plus a request handler, so a stable key prevents duplicate in-app and browser
# notifications without suppressing ordinary conversation/status updates.
IDEMPOTENT_PUSH_EVENTS = {
    "booking_created", "booking_confirmed", "booking_expired", "booking_completed",
    "payment_success", "payment_received", "payment_captured", "payment_failed",
    "payment_refunded", "cancellation_requested", "cancellation_approved",
    "cancellation_rejected", "refund_processed", "invoice_generated",
    "supplier_booking_assigned", "tour_approved", "tour_rejected",
}


def _is_admin(actor: "User | None") -> bool:
    if not actor or not actor.role:
        return True
    slug = actor.role.slug or ""
    # A substring check here means "affiliate" matched none of these and
    # fell through to True (i.e. treated as admin) -- affiliates could see
    # and modify every user's notifications. List every non-admin portal
    # role explicitly instead of trying to substring-match them.
    return not any(marker in slug for marker in ("supplier", "agent", "customer", "affiliate", "reseller"))


def serialize_notification(n: Notification) -> dict:
    return {"id": n.id, "user_id": n.user_id, "notification_type": n.notification_type, "title": n.title, "message": n.message, "channel": n.channel, "status": n.status, "is_read": bool(n.is_read), "entity_type": n.entity_type, "entity_id": n.entity_id, "metadata": n.metadata_json, "sent_at": n.sent_at, "read_at": n.read_at, "created_at": n.created_at}


def create_notification(db: Session, data: NotificationCreate):
    # Manual/admin-created in-app notifications follow exactly the same
    # committed-after-transaction browser-push path as lifecycle events.
    n = enqueue_notification(
        db,
        user_id=data.user_id,
        notification_type=data.notification_type,
        title=data.title,
        message=data.message,
        channel=data.channel,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        metadata=data.metadata,
    )
    db.commit()
    db.refresh(n)
    return serialize_notification(n)


def list_notifications(
    db: Session,
    page: int = 1,
    limit: int = 20,
    user_id: int | None = None,
    is_read: str = "",
    entity_type: str = "",
    entity_id: int | None = None,
    notification_type: str = "",
    actor: "User | None" = None,
):
    query = db.query(Notification)
    if not _is_admin(actor):
        user_id = actor.id
    if user_id:
        query = query.filter(Notification.user_id == user_id)
    if entity_type:
        query = query.filter(Notification.entity_type == entity_type.strip().lower())
    if entity_id:
        query = query.filter(Notification.entity_id == entity_id)
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type.strip().lower())
    if is_read != "":
        expected_read_state = 1 if is_read in {"1", "true", "yes"} else 0
        query = query.filter(Notification.is_read == expected_read_state)
    query = query.order_by(Notification.id.desc())
    total = query.count()
    items = [serialize_notification(notification) for notification in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def mark_all_read(db: Session, user_id: int | None, actor: "User | None" = None) -> int:
    if not _is_admin(actor):
        # Non-admins can only ever mark their own notifications, regardless
        # of what user_id (if any) was requested.
        user_id = actor.id
    query = db.query(Notification).filter(Notification.is_read == 0)
    if user_id:
        query = query.filter(Notification.user_id == user_id)
    # user_id omitted by an admin means "mark every user's notifications as
    # read" - a genuine platform-wide action, not scoped to one account.
    updated = query.update({"is_read": 1, "read_at": utcnow()}, synchronize_session=False)
    db.commit()
    return updated


def mark_read(db: Session, notification_id: int, actor: "User | None" = None):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not _is_admin(actor) and n.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Notification access denied")
    n.is_read = 1
    n.read_at = utcnow()
    db.commit()
    db.refresh(n)
    return serialize_notification(n)


MAX_NOTIFICATION_RETRIES = 5


def retry_notification(db: Session, notification_id: int):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")

    retry_count = (
        db.query(NotificationLog)
        .filter(NotificationLog.notification_id == notification_id)
        .count()
    )
    if retry_count >= MAX_NOTIFICATION_RETRIES:
        raise HTTPException(
            status_code=429,
            detail=f"Notification has already been retried {retry_count} times (max {MAX_NOTIFICATION_RETRIES}).",
        )

    n.status = "sent"
    n.sent_at = utcnow()
    db.add(NotificationLog(notification_id=n.id, channel=n.channel, status="sent", response="manual retry"))
    if n.channel == "in_app":
        from app.services.notifications_push import queue_push
        queue_push(
            db,
            notification_id=n.id,
            user_id=n.user_id,
            title=n.title,
            body=n.message,
            url=(n.metadata_json or {}).get("action_url") or "/",
        )
    db.commit()
    db.refresh(n)
    return serialize_notification(n)


def _notification_url(db: Session, user_id: int | None, entity_type: str | None, entity_id: int | None) -> str | None:
    """Resolve only verified portal routes; never guess a deep link."""
    if not user_id or not entity_type or not entity_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    slug = (user.role.slug if user and user.role else "").lower()
    booking_id = entity_id if entity_type == "booking" else None
    if entity_type == "payment":
        from app.models.payments import Payment
        booking_id = (db.query(Payment.booking_id).filter(Payment.id == entity_id).scalar())
    elif entity_type == "invoice":
        from app.models.invoices import Invoice
        booking_id = (db.query(Invoice.booking_id).filter(Invoice.id == entity_id).scalar())
    elif entity_type == "cancellation_request":
        from app.models.cancellations import CancellationRequest
        booking_id = (db.query(CancellationRequest.booking_id).filter(CancellationRequest.id == entity_id).scalar())
    if booking_id:
        if "supplier" in slug:
            return f"/supplier/bookings/{booking_id}"
        if "agent" in slug or "reseller" in slug:
            return f"/agent/bookings/{booking_id}"
        if "customer" in slug:
            return f"/customer/bookings/{booking_id}"
        if "admin" in slug:
            return f"/admin/bookings/{booking_id}"
    if "admin" in slug:
        admin_paths = {"supplier": "suppliers", "agent": "agents", "affiliate": "affiliates", "tour": "tours", "tour_version": "tours"}
        if entity_type in admin_paths:
            return f"/admin/{admin_paths[entity_type]}/{entity_id}"
    return None


def enqueue_notification(db: Session, *, user_id: int | None, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: int | None = None, channel: str = "in_app", metadata: dict | None = None, event_key: str | None = None, event_version: str = "1"):
    event_key = event_key or (notification_type if notification_type in IDEMPOTENT_PUSH_EVENTS else None)
    key = None
    if event_key and user_id and entity_type and entity_id:
        key = f"{event_key}:{entity_type}:{entity_id}:{user_id}:{event_version}"
        existing = db.query(Notification).filter(Notification.idempotency_key == key).first()
        if existing:
            return existing
    details = dict(metadata or {})
    details.setdefault("action_url", _notification_url(db, user_id, entity_type, entity_id))
    n = Notification(user_id=user_id, notification_type=notification_type, title=title, message=message, channel=channel, entity_type=entity_type, entity_id=entity_id, metadata_json=details, event_key=event_key or notification_type, event_version=event_version, idempotency_key=key, status="sent" if channel == "in_app" else "pending", sent_at=utcnow() if channel == "in_app" else None)
    db.add(n)
    db.flush()
    db.add(NotificationLog(notification_id=n.id, channel=channel, status=n.status, response="queued"))
    if channel == "in_app":
        # Also shown as a browser push, once the caller's transaction commits.
        from app.services.notifications_push import queue_push
        queue_push(db, notification_id=n.id, user_id=user_id, title=title, body=message, url=details.get("action_url") or "/")
    return n


def notify_admins(db: Session, *, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: int | None = None, metadata: dict | None = None, event_key: str | None = None, event_version: str = "1"):
    from app.models.users import User
    from app.models.roles import Role
    rows = db.query(User).join(Role, User.role_id == Role.id).filter(Role.slug.in_(["super-admin", "admin"])).all()
    for user in rows:
        enqueue_notification(db, user_id=user.id, notification_type=notification_type, title=title, message=message, entity_type=entity_type, entity_id=entity_id, metadata=metadata, event_key=event_key, event_version=event_version)


