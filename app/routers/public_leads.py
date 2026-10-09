from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.permissions import require_any_permission
from app.database import get_db
from app.models.public_leads import ContactMessage, NewsletterSubscriber
from app.utils.pagination import paginated_response, pagination_params


router = APIRouter(prefix="/public-leads", tags=["Public Leads"])


def _contact_message(row: ContactMessage) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "email": row.email,
        "phone": row.phone,
        "audience": row.audience or "public",
        "enquiry_type": row.enquiry_type,
        "subject": row.subject,
        "message": row.message,
        "is_replied": row.is_replied,
        "created_at": row.created_at,
    }


def _subscriber(row: NewsletterSubscriber) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "is_active": row.is_active,
        "created_at": row.created_at,
    }


@router.get("/contact-enquiries")
def list_contact_enquiries(
    audience: str = "all",
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("settings.view", "view-settings", "messages.view")),
):
    query = db.query(ContactMessage)
    if audience in {"public", "supplier", "agent"}:
        query = query.filter(ContactMessage.audience == audience)
    if params["search"]:
        search = f'%{params["search"]}%'
        query = query.filter(
            or_(
                ContactMessage.name.ilike(search),
                ContactMessage.email.ilike(search),
                ContactMessage.phone.ilike(search),
                ContactMessage.subject.ilike(search),
                ContactMessage.message.ilike(search),
            )
        )
    query = query.order_by(ContactMessage.created_at.desc(), ContactMessage.id.desc())
    total = query.count()
    rows = query.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()
    return {"status": "success", "data": paginated_response(
        items=rows, total=total, page=params["page"], limit=params["limit"], serializer=_contact_message
    )}


@router.get("/newsletter-subscribers")
def list_newsletter_subscribers(
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("settings.view", "view-settings", "messages.view")),
):
    query = db.query(NewsletterSubscriber)
    if params["search"]:
        query = query.filter(NewsletterSubscriber.email.ilike(f'%{params["search"]}%'))
    query = query.order_by(NewsletterSubscriber.created_at.desc(), NewsletterSubscriber.id.desc())
    total = query.count()
    rows = query.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()
    return {"status": "success", "data": paginated_response(
        items=rows, total=total, page=params["page"], limit=params["limit"], serializer=_subscriber
    )}
