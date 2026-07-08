from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.affiliates import Affiliate
from app.schemas.affiliates import AffiliateApiLinkRequest, AffiliateCreate, AffiliateUpdate
from app.services.audit import log_audit
from app.utils.operations import RejectRequest, approve_item, code_for, get_or_404, relationship_list, reject_item, simple_paginate
from app.models.users import User


def _document(item):
    return {key: getattr(item, key) for key in ["id", "document_type", "document_name", "file_path", "file_size", "mime_type", "status", "uploaded_at", "reviewed_at", "reviewed_by"]}


def serialize_affiliate(item: Affiliate):
    country = item.country
    city = item.city
    return {
        "id": item.id,
        "user_id": item.user_id,
        "affiliate_code": item.affiliate_code,
        "code": item.affiliate_code,
        "business_type": item.business_type,
        "name": item.name,
        "email": item.email,
        "phone": item.phone,
        "website_url": item.website_url,
        "country_id": item.country_id,
        "city_id": item.city_id,
        "country_name": country.country_name if country else "",
        "city_name": city.city_name if city else "",
        "status": item.status,
        "approval_status": item.approval_status,
        "rejection_reason": item.rejection_reason,
        "admin_comments": item.admin_comments,
        "api_link": item.api_link,
        "approved_at": item.approved_at,
        "approved_by": item.approved_by,
        "rejected_at": item.rejected_at,
        "rejected_by": item.rejected_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "documents": relationship_list(item.documents, _document),
        "marketing_info": {
            "promotion_methods": item.marketing_info.promotion_methods,
            "estimated_monthly_bookings": item.marketing_info.estimated_monthly_bookings,
            "existing_audience_size": item.marketing_info.existing_audience_size,
            "social_media_profiles": item.marketing_info.social_media_profiles,
            "existing_travel_platforms_used": item.marketing_info.existing_travel_platforms_used,
        } if item.marketing_info else None,
        "invoicing": {
            "contact_name": item.invoicing.contact_name,
            "email": item.invoicing.email,
            "phone": item.invoicing.phone,
            "account_name": item.invoicing.account_name,
            "account_number": item.invoicing.account_number,
            "bank_name": item.invoicing.bank_name,
            "country_id": item.invoicing.country_id,
            "tax_number": item.invoicing.tax_number,
        } if item.invoicing else None,
    }


def list_affiliates(db: Session, page: int, limit: int, search: str = "", country_id: str = "", status: str = "", approval_status: str = ""):
    query = db.query(Affiliate)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(Affiliate.affiliate_code.ilike(pattern), Affiliate.name.ilike(pattern), Affiliate.email.ilike(pattern), Affiliate.phone.ilike(pattern)))
    if country_id:
        query = query.filter(Affiliate.country_id == int(country_id))
    if status:
        query = query.filter(Affiliate.status == status.strip().lower())
    if approval_status:
        query = query.filter(Affiliate.approval_status == approval_status.strip().lower())
    return simple_paginate(query.order_by(Affiliate.id.desc()), page, limit, serialize_affiliate)


def get_affiliate(db: Session, affiliate_id: int):
    return get_or_404(db, Affiliate, affiliate_id, "Affiliate")


def create_affiliate(db: Session, data: AffiliateCreate, actor: User, request: Request | None = None):
    item = Affiliate(**data.model_dump())
    # Auto-link to existing user account if email matches
    linked_user = db.query(User).filter(User.email == str(data.email).strip().lower()).first()
    if linked_user:
        item.user_id = linked_user.id
    db.add(item)
    db.flush()
    item.affiliate_code = code_for("TVA-AFF", item.id)
    log_audit(db, actor=actor, action="create_affiliate", entity_type="affiliate", entity_id=item.id, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item)


def update_affiliate(db: Session, affiliate_id: int, data: AffiliateUpdate, actor: User, request: Request | None = None):
    item = get_affiliate(db, affiliate_id)
    old = serialize_affiliate(item)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, key, str(value).strip() if isinstance(value, str) else value)
    log_audit(db, actor=actor, action="update_affiliate", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item)


def approve_affiliate(db: Session, affiliate_id: int, actor: User, request: Request | None = None):
    return approve_item(db, get_affiliate(db, affiliate_id), actor, "affiliate", serialize_affiliate, request)


def reject_affiliate(db: Session, affiliate_id: int, data: RejectRequest, actor: User, request: Request | None = None):
    return reject_item(db, get_affiliate(db, affiliate_id), data, actor, "affiliate", serialize_affiliate, request)


def update_affiliate_api_link(db: Session, affiliate_id: int, data: AffiliateApiLinkRequest, actor: User, request: Request | None = None):
    item = get_affiliate(db, affiliate_id)
    old = serialize_affiliate(item)
    item.api_link = data.api_link
    log_audit(db, actor=actor, action="update_affiliate_api_link", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item)
