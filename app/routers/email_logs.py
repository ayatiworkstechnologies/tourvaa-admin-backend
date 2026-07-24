from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.permissions import require_any_permission
from app.database import get_db
from app.models.bookings import EmailLog
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
