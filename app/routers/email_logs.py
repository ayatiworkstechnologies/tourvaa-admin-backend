from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.permissions import require_any_permission
from app.database import get_db
from app.models.bookings import EmailLog
from app.models.notifications import NotificationDelivery
from app.models.users import User
from app.services.audit import log_audit
from app.services.notification_delivery import STALE_PENDING_AFTER, STALE_PROCESSING_AFTER, _schedule_after_commit
from app.utils.money import as_aware_utc, utcnow
from app.utils.pagination import paginated_response, pagination_params


router = APIRouter(prefix="/email-logs", tags=["Email Logs"])


def serialize_email_log(row: EmailLog) -> dict:
    return {
        "id": row.id,
        "recipient_email": row.recipient_email,
        "subject": row.subject,
        "template_key": row.template_key,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "status": row.status,
        "error_message": row.error_message,
        "sent_at": row.sent_at,
        "created_at": row.created_at,
    }


def serialize_delivery(row: NotificationDelivery) -> dict:
    now = utcnow()
    stale = (
        row.status == "pending" and row.updated_at and as_aware_utc(row.updated_at) <= now - STALE_PENDING_AFTER
    ) or (
        row.status == "processing" and (
            (row.lease_expires_at and as_aware_utc(row.lease_expires_at) <= now)
            or (row.updated_at and as_aware_utc(row.updated_at) <= now - STALE_PROCESSING_AFTER)
        )
    )
    return {
        "id": row.id,
        "event_type": row.event_type,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "recipient_type": row.recipient_type,
        "recipient_email": row.recipient_email,
        "template_key": row.template_key,
        "subject": row.subject,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "next_attempt_at": row.next_attempt_at,
        "lease_expires_at": row.lease_expires_at,
        "smtp_accepted_at": row.smtp_accepted_at,
        "exhausted_at": row.exhausted_at,
        "error_message": row.error_message,
        "is_stale": bool(stale),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/deliveries")
def list_email_deliveries(
    params: dict = Depends(pagination_params),
    status: str = Query(default=""),
    stale_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("email_templates.view", "view-email", "activity_logs.view")),
):
    query = db.query(NotificationDelivery)
    if params["search"]:
        pattern = f"%{params['search']}%"
        query = query.filter(or_(NotificationDelivery.recipient_email.ilike(pattern), NotificationDelivery.event_type.ilike(pattern)))
    if status:
        query = query.filter(NotificationDelivery.status == status.strip().lower())
    if stale_only:
        now = utcnow()
        query = query.filter(or_(
            (NotificationDelivery.status == "pending") & (NotificationDelivery.updated_at <= now - STALE_PENDING_AFTER),
            (NotificationDelivery.status == "processing") & (NotificationDelivery.lease_expires_at <= now),
        ))
    total = query.count()
    rows = query.order_by(NotificationDelivery.id.desc()).offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()
    return {"status": "success", "data": [serialize_delivery(row) for row in rows], **paginated_response(items=rows, total=total, page=params["page"], limit=params["limit"], serializer=serialize_delivery)}


@router.post("/deliveries/{delivery_id}/retry")
def retry_email_delivery(
    delivery_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_any_permission("update-email", "activity_logs.view")),
):
    row = db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Email delivery not found")
    if row.status not in {"failed", "exhausted"}:
        raise HTTPException(status_code=409, detail="Only failed or exhausted deliveries can be retried manually")
    if not row.payload_json:
        row.status = "manual_review"
        row.error_message = "Delivery payload is unavailable; automatic replay is unsafe."
        db.commit()
        raise HTTPException(status_code=409, detail="This legacy delivery has no replay payload and requires manual review")
    old_status = row.status
    row.status = "failed"
    row.attempt_count = 0
    row.next_attempt_at = None
    row.exhausted_at = None
    row.lease_token = None
    row.lease_expires_at = None
    log_audit(db, actor=actor, action="retry_email_delivery", entity_type="notification_delivery", entity_id=row.id, old_values={"status": old_status}, new_values={"status": "failed"}, request=request)
    _schedule_after_commit(db, row.id, None)
    db.commit()
    return {"status": "success", "message": "Email delivery queued for retry", "data": serialize_delivery(row)}


@router.get("")
@router.get("/")
def list_email_logs(
    params: dict = Depends(pagination_params),
    status: str = Query(default=""),
    entity_type: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("email_templates.view", "view-email", "activity_logs.view")),
):
    query = db.query(EmailLog)

    if params["search"]:
        query = query.filter(EmailLog.recipient_email.ilike(f"%{params['search']}%"))
    if status:
        query = query.filter(EmailLog.status == status.strip().lower())
    if entity_type:
        query = query.filter(EmailLog.entity_type == entity_type.strip())

    query = query.order_by(EmailLog.id.desc())
    total = query.count()
    items = query.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()

    return {
        "status": "success",
        "data": [serialize_email_log(row) for row in items],
        **paginated_response(
            items=items,
            total=total,
            page=params["page"],
            limit=params["limit"],
            serializer=serialize_email_log,
        ),
    }
