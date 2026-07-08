import json
from pathlib import Path
from sqlalchemy.orm import Session
from pywebpush import webpush, WebPushException

from app.config import settings
from app.models.notifications import PushSubscription


def _vapid_pem_path() -> str:
    p = Path(settings.VAPID_PRIVATE_KEY_FILE)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[4] / p
    return str(p)


def save_subscription(db: Session, *, endpoint: str, p256dh: str, auth: str, user_id: int | None = None) -> PushSubscription:
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        if user_id:
            existing.user_id = user_id
        db.commit()
        db.refresh(existing)
        return existing

    sub = PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth, user_id=user_id)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def delete_subscription(db: Session, endpoint: str, user_id: int | None = None) -> None:
    query = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint)
    if user_id is not None:
        query = query.filter(PushSubscription.user_id == user_id)
    query.delete()
    db.commit()


def send_push(sub: PushSubscription, *, title: str, body: str, url: str = "/", icon: str = "/icon.png", action: str | None = None, phone: str | None = None, wa_msg: str | None = None) -> bool:
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY_FILE:
        return False

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
            vapid_private_key=_vapid_pem_path(),
            vapid_claims={"sub": settings.VAPID_MAILTO},
        )
        return True
    except WebPushException:
        return False


def broadcast_push(db: Session, *, title: str, body: str, url: str = "/", icon: str = "/icon.png", user_ids: list[int] | None = None) -> dict:
    query = db.query(PushSubscription)
    if user_ids:
        query = query.filter(PushSubscription.user_id.in_(user_ids))
    subs = query.all()

    sent, failed, stale = 0, 0, []
    for sub in subs:
        ok = send_push(sub, title=title, body=body, url=url, icon=icon)
        if ok:
            sent += 1
        else:
            failed += 1
            stale.append(sub.endpoint)

    for endpoint in stale:
        delete_subscription(db, endpoint)

    return {"sent": sent, "failed": failed}
