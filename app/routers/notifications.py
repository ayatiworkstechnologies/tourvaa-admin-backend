from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import require_any_permission, get_current_user
from app.utils.pagination import pagination_params
from app.schemas.notifications import NotificationCreate
from app.services.notifications import create_notification, list_notifications, mark_all_read, mark_read, retry_notification
from app.services.notifications_push import save_subscription, delete_subscription, broadcast_push

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class PushSubscribeBody(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushBroadcastBody(BaseModel):
    title: str
    body: str
    url: str = "/"
    icon: str = "/icon.png"
    user_ids: list[int] | None = None

@router.get("")
@router.get("/")
def notifications(
    params: dict = Depends(pagination_params),
    user_id: int = Query(default=0),
    is_read: str = Query(default=""),
    entity_type: str = Query(default=""),
    entity_id: int = Query(default=0),
    notification_type: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("notifications.view")),
):
    return {
        "status": "success",
        **list_notifications(
            db,
            params["page"],
            params["limit"],
            user_id or None,
            is_read,
            entity_type,
            entity_id or None,
            notification_type,
            actor=current_user,
        ),
    }


@router.patch("/mark-all-read")
def mark_all_read_route(user_id: int = Query(...), db: Session = Depends(get_db), current_user=Depends(require_any_permission("notifications.view"))):
    updated = mark_all_read(db, user_id, actor=current_user)
    return {"status": "success", "data": {"updated": updated}}

@router.post("")
def create(data: NotificationCreate, db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.manage"))):
    return {"status": "success", "data": create_notification(db, data)}

@router.patch("/{notification_id}/read")
def read(notification_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("notifications.view"))):
    return {"status": "success", "data": mark_read(db, notification_id, actor=current_user)}

@router.post("/{notification_id}/retry")
def retry(notification_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.retry", "notifications.manage"))):
    return {"status": "success", "data": retry_notification(db, notification_id)}


@router.post("/push/subscribe")
def push_subscribe(body: PushSubscribeBody, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user_id = current_user.id if current_user else None
    save_subscription(db, endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth, user_id=user_id)
    return {"status": "success"}


@router.delete("/push/subscribe")
def push_unsubscribe(body: PushSubscribeBody, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    delete_subscription(db, body.endpoint, user_id=current_user.id if current_user else None)
    return {"status": "success"}


@router.post("/push/broadcast")
def push_broadcast(body: PushBroadcastBody, db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.manage"))):
    result = broadcast_push(db, title=body.title, body=body.body, url=body.url, icon=body.icon, user_ids=body.user_ids)
    return {"status": "success", "data": result}
