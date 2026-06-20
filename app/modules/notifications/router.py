from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.notifications.schemas import NotificationCreate
from app.modules.notifications.service import create_notification, list_notifications, mark_read, retry_notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("")
@router.get("/")
def notifications(params: dict = Depends(pagination_params), user_id: int = Query(default=0), is_read: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.view"))):
    return {"status": "success", **list_notifications(db, params["page"], params["limit"], user_id or None, is_read)}

@router.post("")
def create(data: NotificationCreate, db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.manage"))):
    return {"status": "success", "data": create_notification(db, data)}

@router.patch("/{notification_id}/read")
def read(notification_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.view"))):
    return {"status": "success", "data": mark_read(db, notification_id)}

@router.post("/{notification_id}/retry")
def retry(notification_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("notifications.retry", "notifications.manage"))):
    return {"status": "success", "data": retry_notification(db, notification_id)}
