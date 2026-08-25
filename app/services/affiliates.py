from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.affiliates import Affiliate, AffiliateDocument
from app.schemas.affiliates import AffiliateApiLinkRequest, AffiliateCreate, AffiliateDocumentReviewRequest, AffiliateUpdate
from app.services.audit import log_audit
from app.utils.operations import RejectRequest, approve_item, get_or_404, relationship_list, reject_item, simple_paginate
from app.auth.security import hash_password
from app.models.roles import Role
from app.models.users import User, UserRole
from app.utils.money import utcnow

# Smaller than SUPPLIER_DOCUMENT_TYPES -- affiliates are individuals/small
# marketers promoting Tourvaa, not running a tour-operating business, so
# there's no equivalent of a trade license / company registration to ask for.
AFFILIATE_DOCUMENT_TYPES = {
    "identity_proof": {"label": "Identity Proof (Passport / National ID)", "required": True},
    "bank_details": {"label": "Bank Account Details / Cheque", "required": True},
    "tax_certificate": {"label": "Tax Registration Certificate (if applicable)", "required": False},
}
REQUIRED_AFFILIATE_DOCUMENT_TYPES = {key for key, metadata in AFFILIATE_DOCUMENT_TYPES.items() if metadata["required"]}


def _document(item):
    file_path = item.file_path or ""
    if file_path.startswith("/private-documents/") or file_path.startswith("cloudinary:"):
        file_url = f"/api/private-documents/affiliate/{item.id}"
    elif file_path and not file_path.startswith("http"):
        file_url = file_path if file_path.startswith("/") else "/storage/" + file_path
    else:
        file_url = file_path
    data = {key: getattr(item, key) for key in ["id", "document_type", "document_name", "file_path", "file_size", "mime_type", "status", "rejection_reason", "uploaded_at", "reviewed_at", "reviewed_by"]}
    data["file_url"] = file_url
    return data


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
        "commission_percentage": str(item.commission_percentage),
        "rejection_reason": item.rejection_reason,
        "admin_comments": item.admin_comments,
        "api_link": item.api_link,
        "approved_at": item.approved_at,
        "approved_by": item.approved_by,
        "rejected_at": item.rejected_at,
        "rejected_by": item.rejected_by,
        "commission_accepted_at": item.commission_accepted_at,
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


def accept_affiliate_commission(db: Session, affiliate_id: int, actor: User, request: Request | None = None):
    """Records that the affiliate clicked "Yes" on the post-login commission-
    consent popup (CommissionConsentModal). Affiliates have no document
    upload endpoint today, so this just unblocks the portal generally --
    see affiliate/layout.tsx. Also seeds the admin-configured default rate
    onto Affiliate.commission_percentage (the real payout field) if it's
    still at its untouched default of 0 -- self-registration always creates
    affiliates at 0 (see AffiliateCreate), so without this the accepted
    rate would just be a display number with no effect on payouts. Skipped
    if an admin already gave this affiliate a deliberate non-zero rate via
    update_affiliate before they ever logged in."""
    from decimal import Decimal
    from app.services.settings import get_affiliate_default_commission
    item = get_affiliate(db, affiliate_id)
    if item.commission_accepted_at is None:
        item.commission_accepted_at = utcnow()
        if Decimal(str(item.commission_percentage or 0)) == 0:
            item.commission_percentage = get_affiliate_default_commission(db)
        log_audit(db, actor=actor, action="accept_affiliate_commission", entity_type="affiliate", entity_id=item.id, request=request)
        db.commit()
        db.refresh(item)
    return serialize_affiliate(item)


def create_affiliate(db: Session, data: AffiliateCreate, actor: User, request: Request | None = None):
    affiliate_data = data.model_dump(exclude={"password"})
    email = str(data.email).strip().lower()
    linked_user = db.query(User).filter(User.email == email).first()
    if data.password is not None:
        if linked_user:
            raise HTTPException(status_code=409, detail="Email already exists")
        role = db.query(Role).filter(Role.slug == "affiliate", Role.is_active == True).first()
        if not role:
            raise HTTPException(status_code=400, detail="Affiliate accounts are not available")
        now = utcnow()
        linked_user = User(
            name=data.name,
            email=email,
            phone=data.phone,
            password=hash_password(data.password),
            role_id=role.id,
            user_type="AFFILIATE",
            is_active=True,
            approval_status="pending",
            email_verified=True,
            email_verified_at=now,
            password_created_at=now,
            account_status="ACTIVE",
        )
        db.add(linked_user)
        db.flush()
        db.add(UserRole(user_id=linked_user.id, role_id=role.id))
    if linked_user:
        affiliate_data["user_id"] = linked_user.id
    item = Affiliate(**affiliate_data)
    db.add(item)
    db.flush()
    item.affiliate_code = f"{item.id:05d}"
    log_audit(db, actor=actor, action="create_affiliate", entity_type="affiliate", entity_id=item.id, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item)


def update_affiliate(db: Session, affiliate_id: int, data: AffiliateUpdate, actor: User, request: Request | None = None):
    item = get_affiliate(db, affiliate_id)
    old = serialize_affiliate(item)
    if data.commission_percentage is not None:
        from app.services.settings import get_affiliate_commission_max
        from decimal import Decimal
        maximum = get_affiliate_commission_max(db)
        if Decimal(str(data.commission_percentage)) > maximum:
            raise HTTPException(status_code=400, detail=f"Affiliate commission cannot exceed the platform maximum of {maximum}%")

    update_data = data.model_dump(exclude_unset=True)
    marketing_data = update_data.pop("marketing_info", None)
    invoicing_data = update_data.pop("invoicing", None)

    for key, value in update_data.items():
        if value is not None:
            setattr(item, key, str(value).strip() if isinstance(value, str) else value)

    if marketing_data:
        if not item.marketing_info:
            from app.models.affiliates import AffiliateMarketingInfo
            item.marketing_info = AffiliateMarketingInfo(affiliate_id=item.id)
            db.add(item.marketing_info)
        for k, v in marketing_data.items():
            if v is not None:
                setattr(item.marketing_info, k, v)

    if invoicing_data:
        if not item.invoicing:
            from app.models.affiliates import AffiliateInvoicing
            item.invoicing = AffiliateInvoicing(affiliate_id=item.id)
            db.add(item.invoicing)
        for k, v in invoicing_data.items():
            if v is not None:
                setattr(item.invoicing, k, v)

    log_audit(db, actor=actor, action="update_affiliate", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item)


def submit_affiliate_verification(db: Session, user: User, request: Request | None = None):
    """Self-service: an affiliate signals their profile/documents are ready
    for admin review. Mirrors services.suppliers._submit_supplier_verification."""
    item = db.query(Affiliate).filter(Affiliate.user_id == user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Affiliate profile not found")
    if (item.approval_status or "").lower() == "approved":
        raise HTTPException(status_code=409, detail="Affiliate is already approved")
    old = serialize_affiliate(item)
    item.approval_status = "pending"
    item.status = "active"
    item.rejection_reason = None
    log_audit(db, actor=user, action="submit_affiliate_verification", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    try:
        from app.services.notifications import notify_admins
        notify_admins(db, notification_type="affiliate_submitted", title="Affiliate Submitted for Review", message=f"Affiliate '{item.name}' submitted their profile for review.", entity_type="affiliate", entity_id=item.id)
        db.commit()
    except Exception:
        pass
    return serialize_affiliate(item)


def review_affiliate_document(db: Session, document_id: int, data: AffiliateDocumentReviewRequest, actor: User, request: Request | None = None):
    doc = db.query(AffiliateDocument).filter(AffiliateDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = data.status
    doc.rejection_reason = data.rejection_reason if data.status == "rejected" else None
    doc.reviewed_at = utcnow()
    doc.reviewed_by = actor.id
    log_audit(db, actor=actor, action="review_affiliate_document", entity_type="affiliate_document", entity_id=doc.id, new_values={"status": doc.status, "rejection_reason": doc.rejection_reason}, request=request)
    db.commit()
    db.refresh(doc)
    return _document(doc)


def approve_affiliate(db: Session, affiliate_id: int, actor: User, request: Request | None = None):
    return approve_item(db, get_affiliate(db, affiliate_id), actor, "affiliate", serialize_affiliate, request)


def reject_affiliate(db: Session, affiliate_id: int, data: RejectRequest, actor: User, request: Request | None = None):
    return reject_item(db, get_affiliate(db, affiliate_id), data, actor, "affiliate", serialize_affiliate, request)


def activate_affiliate(db: Session, affiliate_id: int, actor: User, request: Request | None = None):
    """Re-enable an already-approved affiliate's operational access (undo a
    prior suspend) without re-running the full approval review."""
    item = get_affiliate(db, affiliate_id)
    if (item.approval_status or "").lower() != "approved":
        raise HTTPException(status_code=400, detail="Only an approved affiliate can be activated")
    old = serialize_affiliate(item)
    item.status = "active"
    log_audit(db, actor=actor, action="activate_affiliate", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    try:
        from app.utils.notification_triggers import notify_affiliate_activated
        notify_affiliate_activated(db, affiliate_id=item.id, affiliate_name=item.name, user_id=item.user_id)
        db.commit()
    except Exception:
        pass
    return serialize_affiliate(item)


def suspend_affiliate(db: Session, affiliate_id: int, data, actor: User, request: Request | None = None):
    """Block link generation/commission for an affiliate without rejecting
    their application - status flips to inactive; approval_status is left
    untouched so activate_affiliate can restore access later."""
    item = get_affiliate(db, affiliate_id)
    old = serialize_affiliate(item)
    item.status = "inactive"
    item.admin_comments = data.reason
    log_audit(db, actor=actor, action="suspend_affiliate", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    try:
        from app.utils.notification_triggers import notify_affiliate_suspended
        notify_affiliate_suspended(db, affiliate_id=item.id, affiliate_name=item.name, reason=data.reason, user_id=item.user_id)
        db.commit()
    except Exception:
        pass
    return serialize_affiliate(item)


def update_affiliate_api_link(db: Session, affiliate_id: int, data: AffiliateApiLinkRequest, actor: User, request: Request | None = None):
    item = get_affiliate(db, affiliate_id)
    old = serialize_affiliate(item)
    item.api_link = data.api_link
    log_audit(db, actor=actor, action="update_affiliate_api_link", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item)
