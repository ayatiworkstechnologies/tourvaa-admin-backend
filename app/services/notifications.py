from math import ceil
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.utils.money import utcnow
from app.models.notifications import Notification, NotificationLog
from app.schemas.notifications import NotificationCreate
from app.models.users import User


def _is_admin(actor: "User | None") -> bool:
    if not actor or not actor.role:
        return True
    slug = actor.role.slug or ""
    return not any(marker in slug for marker in ("supplier", "agent", "customer"))


def serialize_notification(n: Notification) -> dict:
    return {"id": n.id, "user_id": n.user_id, "notification_type": n.notification_type, "title": n.title, "message": n.message, "channel": n.channel, "status": n.status, "is_read": bool(n.is_read), "entity_type": n.entity_type, "entity_id": n.entity_id, "metadata": n.metadata_json, "sent_at": n.sent_at, "read_at": n.read_at, "created_at": n.created_at}


def create_notification(db: Session, data: NotificationCreate):
    n = Notification(user_id=data.user_id, notification_type=data.notification_type, title=data.title, message=data.message, channel=data.channel, entity_type=data.entity_type, entity_id=data.entity_id, metadata_json=data.metadata, status="sent" if data.channel == "in_app" else "pending", sent_at=utcnow() if data.channel == "in_app" else None)
    db.add(n)
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
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def mark_all_read(db: Session, user_id: int, actor: "User | None" = None) -> int:
    if not _is_admin(actor):
        user_id = actor.id
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == 0)
        .update({"is_read": 1, "read_at": utcnow()}, synchronize_session=False)
    )
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
    db.commit()
    db.refresh(n)
    return serialize_notification(n)


def enqueue_notification(db: Session, *, user_id: int | None, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: int | None = None, channel: str = "in_app", metadata: dict | None = None):
    n = Notification(user_id=user_id, notification_type=notification_type, title=title, message=message, channel=channel, entity_type=entity_type, entity_id=entity_id, metadata_json=metadata, status="sent" if channel == "in_app" else "pending", sent_at=utcnow() if channel == "in_app" else None)
    db.add(n)
    db.flush()
    db.add(NotificationLog(notification_id=n.id, channel=channel, status=n.status, response="queued"))
    return n


def notify_admins(db: Session, *, notification_type: str, title: str, message: str, entity_type: str | None = None, entity_id: int | None = None):
    from app.models.users import User
    from app.models.roles import Role
    rows = db.query(User).join(Role, User.role_id == Role.id).filter(Role.slug.in_(["super-admin", "admin"])).all()
    for user in rows:
        enqueue_notification(db, user_id=user.id, notification_type=notification_type, title=title, message=message, entity_type=entity_type, entity_id=entity_id)


