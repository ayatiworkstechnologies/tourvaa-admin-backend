from fastapi import BackgroundTasks, HTTPException, Request
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

AFFILIATE_DOCUMENT_TYPES = {
    "company_registration": {"label": "Business Registration Certificate", "required": True},
    "iata_accreditation": {"label": "IATA Accreditation / Travel Licence", "required": True},
    "industry_certification": {"label": "Industry Certifications", "required": False},
    "other_licences": {"label": "Other Licences", "required": False},
    "supporting_documents": {"label": "Additional Supporting Documents", "required": False},
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


def _mask_bank_identifier(value: str | None) -> str:
    value = (value or "").strip()
    return f"{'*' * max(0, len(value) - 4)}{value[-4:]}" if value else ""


def serialize_affiliate(item: Affiliate, *, mask_bank_details: bool = False):
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
            "preferred_payment_method": item.invoicing.preferred_payment_method,
            "account_name": item.invoicing.account_name,
            "account_number": _mask_bank_identifier(item.invoicing.account_number) if mask_bank_details else item.invoicing.account_number,
            "bank_name": item.invoicing.bank_name,
            "bank_branch": item.invoicing.bank_branch,
            "swift_code": item.invoicing.swift_code,
            "iban": _mask_bank_identifier(item.invoicing.iban) if mask_bank_details else item.invoicing.iban,
            "country_id": item.invoicing.country_id,
            "bank_details_locked": any(getattr(item.invoicing, field, None) for field in ("preferred_payment_method", "account_name", "account_number", "bank_name", "bank_branch", "swift_code", "iban")),
            "bank_edit_request_pending": bool(item.invoicing.bank_edit_requested_at),
            "bank_edit_unlocked": bool(item.invoicing.bank_edit_unlocked_at),
            "tax_number": item.invoicing.tax_number,
            "billing_address": item.invoicing.billing_address,
            "billing_city": item.invoicing.billing_city,
            "billing_state": item.invoicing.billing_state,
            "billing_postal_code": item.invoicing.billing_postal_code,
        } if item.invoicing else None,
    }


def list_affiliates(db: Session, page: int, limit: int, search: str = "", country_id: str = "", status: str = "", approval_status: str = "", start_date: str = "", end_date: str = "", sort_by: str = ""):
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
    if start_date:
        query = query.filter(Affiliate.created_at >= start_date)
    if end_date:
        query = query.filter(Affiliate.created_at <= f"{end_date} 23:59:59")
    if sort_by == "oldest":
        query = query.order_by(Affiliate.id.asc())
    elif sort_by == "name_az":
        query = query.order_by(Affiliate.name.asc())
    else:
        query = query.order_by(Affiliate.id.desc())
    return simple_paginate(query, page, limit, serialize_affiliate)


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
    from app.services.settings import get_affiliate_commission_max, get_affiliate_default_commission
    item = get_affiliate(db, affiliate_id)
    if item.commission_accepted_at is None:
        item.commission_accepted_at = utcnow()
        if Decimal(str(item.commission_percentage or 0)) == 0:
            # Settings can be changed independently.  Do not assign a newly
            # accepting affiliate a default that exceeds the current cap.
            item.commission_percentage = min(
                get_affiliate_default_commission(db),
                get_affiliate_commission_max(db),
            )
        log_audit(db, actor=actor, action="accept_affiliate_commission", entity_type="affiliate", entity_id=item.id, request=request)
        db.commit()
        db.refresh(item)
    return serialize_affiliate(item, mask_bank_details=actor.id == item.user_id)


def create_affiliate(db: Session, data: AffiliateCreate, actor: User, request: Request | None = None):
    if data.commission_percentage is not None:
        from app.services.settings import get_affiliate_commission_max
        from decimal import Decimal
        maximum = get_affiliate_commission_max(db)
        if Decimal(str(data.commission_percentage)) > maximum:
            raise HTTPException(status_code=400, detail=f"Affiliate commission cannot exceed the platform maximum of {maximum}%")
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
    item.affiliate_code = str(item.id)
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

    # country_id represents the invoice/billing country, not an immutable
    # payment credential, so it remains editable after bank details lock.
    bank_fields = {"preferred_payment_method", "account_name", "account_number", "bank_name", "bank_branch", "swift_code", "iban"}
    existing_invoicing = getattr(item, "invoicing", None)
    if actor.id == item.user_id and existing_invoicing and invoicing_data and any(key in bank_fields for key in invoicing_data):
        if any(getattr(existing_invoicing, key, None) for key in bank_fields) and not existing_invoicing.bank_edit_unlocked_at:
            raise HTTPException(status_code=400, detail="Bank details are locked after saving. Contact Tourvaa support to request a change.")

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
        if actor.id == item.user_id and any(key in bank_fields for key in invoicing_data):
            item.invoicing.bank_edit_unlocked_at = None

    log_audit(db, actor=actor, action="update_affiliate", entity_type="affiliate", entity_id=item.id, old_values=old, new_values=serialize_affiliate(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_affiliate(item, mask_bank_details=actor.id == item.user_id)


def request_affiliate_bank_edit(db: Session, affiliate: Affiliate, actor: User, request: Request | None = None):
    if not affiliate.invoicing or not any(getattr(affiliate.invoicing, key, None) for key in ("account_number", "iban", "swift_code")):
        raise HTTPException(status_code=400, detail="Save bank details before requesting an edit")
    if affiliate.invoicing.bank_edit_unlocked_at:
        return serialize_affiliate(affiliate, mask_bank_details=True)
    affiliate.invoicing.bank_edit_requested_at = utcnow()
    log_audit(db, actor=actor, action="request_affiliate_bank_edit", entity_type="affiliate", entity_id=affiliate.id, request=request)
    from app.utils.notification_triggers import notify_bank_detail_edit_requested
    notify_bank_detail_edit_requested(db, partner_type="affiliate", partner_id=affiliate.id, partner_name=affiliate.name)
    db.commit(); db.refresh(affiliate)
    return serialize_affiliate(affiliate, mask_bank_details=True)


def unlock_affiliate_bank_edit(db: Session, affiliate_id: int, actor: User, request: Request | None = None):
    item = get_affiliate(db, affiliate_id)
    if not item.invoicing or not item.invoicing.bank_edit_requested_at:
        raise HTTPException(status_code=409, detail="No pending bank-detail edit request")
    item.invoicing.bank_edit_unlocked_at = utcnow()
    item.invoicing.bank_edit_unlocked_by = actor.id
    item.invoicing.bank_edit_requested_at = None
    log_audit(db, actor=actor, action="unlock_affiliate_bank_edit", entity_type="affiliate", entity_id=item.id, request=request)
    from app.utils.notification_triggers import notify_bank_detail_edit_decision
    notify_bank_detail_edit_decision(db, partner_type="affiliate", partner_id=item.id, partner_name=item.name, user_id=item.user_id, approved=True)
    db.commit(); db.refresh(item)
    return serialize_affiliate(item)


def reject_affiliate_bank_edit(db: Session, affiliate_id: int, reason: str, actor: User, request: Request | None = None):
    item = get_affiliate(db, affiliate_id)
    if not item.invoicing or not item.invoicing.bank_edit_requested_at:
        raise HTTPException(status_code=409, detail="No pending bank-detail edit request")
    item.invoicing.bank_edit_requested_at = None
    log_audit(db, actor=actor, action="reject_affiliate_bank_edit", entity_type="affiliate", entity_id=item.id, new_values={"reason": reason}, request=request)
    from app.utils.notification_triggers import notify_bank_detail_edit_decision
    notify_bank_detail_edit_decision(db, partner_type="affiliate", partner_id=item.id, partner_name=item.name, user_id=item.user_id, approved=False, reason=reason)
    db.commit(); db.refresh(item)
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
        from app.utils.notification_triggers import notify_affiliate_submitted_verification

        notify_affiliate_submitted_verification(
            db,
            affiliate_id=item.id,
            affiliate_name=item.name,
        )
        db.commit()
    except Exception:
        db.rollback()
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


def approve_affiliate(db: Session, affiliate_id: int, actor: User, request: Request | None = None, background_tasks: BackgroundTasks | None = None):
    return approve_item(db, get_affiliate(db, affiliate_id), actor, "affiliate", serialize_affiliate, request, background_tasks)


def reject_affiliate(db: Session, affiliate_id: int, data: RejectRequest, actor: User, request: Request | None = None, background_tasks: BackgroundTasks | None = None):
    return reject_item(db, get_affiliate(db, affiliate_id), data, actor, "affiliate", serialize_affiliate, request, background_tasks)


def activate_affiliate(db: Session, affiliate_id: int, actor: User, request: Request | None = None, background_tasks: BackgroundTasks | None = None):
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
        notify_affiliate_activated(db, affiliate_id=item.id, affiliate_name=item.name, user_id=item.user_id, background_tasks=background_tasks)
        db.commit()
    except Exception:
        pass
    return serialize_affiliate(item)


def suspend_affiliate(db: Session, affiliate_id: int, data, actor: User, request: Request | None = None, background_tasks: BackgroundTasks | None = None):
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
        notify_affiliate_suspended(db, affiliate_id=item.id, affiliate_name=item.name, reason=data.reason, user_id=item.user_id, background_tasks=background_tasks)
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
