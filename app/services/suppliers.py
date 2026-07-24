import logging

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.services.audit import log_audit
from app.utils.operations import (
    PartialApprovalRequest,
    RejectRequest,
    code_for,
    filter_review_query,
    get_or_404,
    relationship_list,
    serialize_common_review,
    simple_paginate,
)
from datetime import datetime

from app.models.suppliers import Supplier, SupplierApprovalHistory, SupplierDocument, SupplierVehicle
from app.schemas.suppliers import (
    DocumentReviewRequest,
    SupplierCreate,
    SupplierMarkupRequest,
    SupplierUpdate,
    VehicleReviewRequest,
)
from app.models.users import User

logger = logging.getLogger(__name__)


def _approval_history(item):
    # supplier_approval_history (migration 20260724_0034) may not exist yet on
    # every deployed database; degrade to an empty history instead of a 500
    # until that migration has run everywhere.
    try:
        history_rows = list(item.approval_history)
    except SQLAlchemyError:
        logger.exception("Failed to load approval_history for supplier %s", item.id)
        return []
    return [
        {
            "id": history.id,
            "from_status": history.from_status,
            "to_status": history.to_status,
            "notes": history.notes,
            "changed_by": history.changed_by,
            "created_at": history.created_at,
        }
        for history in history_rows
    ]


def _contact(item):
    return {key: getattr(item, key) for key in ["id", "contact_name", "designation", "phone", "email", "alternate_phone", "is_primary", "created_at", "updated_at"]}


def _document(item):
    file_path = item.file_path or ""
    if file_path.startswith("/private-documents/") or file_path.startswith("imagekit:"):
        file_url = f"/api/private-documents/supplier/{item.id}"
    elif file_path and not file_path.startswith("http"):
        file_url = file_path if file_path.startswith("/") else "/storage/" + file_path
    else:
        file_url = file_path
    return {
        "id": item.id,
        "document_type": item.document_type,
        "document_name": item.document_name,
        "file_path": item.file_path,
        "file_url": file_url,
        "file_size": item.file_size,
        "mime_type": item.mime_type,
        "status": item.status,
        "rejection_reason": item.rejection_reason,
        "notes": item.rejection_reason,
        "uploaded_at": item.uploaded_at,
        "reviewed_at": item.reviewed_at,
        "reviewed_by": item.reviewed_by,
    }


def _serialize_vehicle(v) -> dict:
    import json
    photos_raw = v.vehicle_photos or ""
    try:
        photos = json.loads(photos_raw) if photos_raw else []
    except Exception:
        photos = [p for p in photos_raw.split(",") if p.strip()]
    return {
        "id": v.id,
        "make": v.make or "",
        "model": v.model or "",
        "vehicle_type": getattr(v, "vehicle_type", "") or "",
        "registration_number": getattr(v, "registration_number", "") or "",
        "year": v.year,
        "capacity": v.capacity,
        "fitness_certificate": v.fitness_certificate or "",
        "insurance_document": v.insurance_document or "",
        "vehicle_photos": photos,
        "approval_status": v.approval_status,
        "rejection_reason": v.rejection_reason,
        "reviewed_at": str(v.reviewed_at) if v.reviewed_at else "",
        "reviewed_by": v.reviewed_by,
        "created_at": str(v.created_at) if v.created_at else "",
    }


def serialize_supplier(item: Supplier):
    data = serialize_common_review(item, "supplier_name", "supplier_code")
    data.update(
        {
            "supplier_type": item.supplier_type,
            "markup_type": item.markup_type,
            "markup_value": item.markup_value,
            "commission_request_type": item.commission_request_type,
            "commission_request_value": item.commission_request_value,
            "commission_request_status": item.commission_request_status,
            "commission_requested_at": item.commission_requested_at,
            "commission_reviewed_at": item.commission_reviewed_at,
            "contacts": relationship_list(item.contacts, _contact),
            "vehicles": relationship_list(item.vehicles, _serialize_vehicle),
            "documents": relationship_list(item.documents, _document),
            "approval_history": _approval_history(item),
            "business_info": {
                "years_in_business": item.business_info.years_in_business,
                "certificate_of_incorporation": item.business_info.certificate_of_incorporation,
                "monthly_customers_count": item.business_info.monthly_customers_count,
                "target_market": item.business_info.target_market,
                "destinations_sold": item.business_info.destinations_sold,
                "gst_tax_number": item.business_info.gst_tax_number,
                "business_registration_number": item.business_info.business_registration_number,
                "approval_status": item.business_info.approval_status,
            } if item.business_info else None,
            "invoicing": {
                "contact_name": item.invoicing.contact_name,
                "email": item.invoicing.email,
                "phone": item.invoicing.phone,
                "account_name": item.invoicing.account_name,
                "account_number": item.invoicing.account_number,
                "bank_name": item.invoicing.bank_name,
                "bank_branch": item.invoicing.bank_branch,
                "swift_code": item.invoicing.swift_code,
                "iban": item.invoicing.iban,
                "country_id": item.invoicing.country_id,
                "tax_number": item.invoicing.tax_number,
            } if item.invoicing else None,
        }
    )
    return data


def list_suppliers(db: Session, page: int, limit: int, search: str = "", country_id: str = "", status: str = "", approval_status: str = "", start_date: str = "", end_date: str = ""):
    base_query = db.query(Supplier).options(
        joinedload(Supplier.country),
        joinedload(Supplier.city),
        joinedload(Supplier.business_info),
        joinedload(Supplier.invoicing),
        selectinload(Supplier.contacts),
        selectinload(Supplier.vehicles),
        selectinload(Supplier.documents),
    )
    query = filter_review_query(base_query, Supplier, search=search, country_id=country_id, status=status, approval_status=approval_status, start_date=start_date, end_date=end_date, name_field="supplier_name")
    return simple_paginate(query, page, limit, serialize_supplier)


def get_supplier(db: Session, supplier_id: int):
    return get_or_404(db, Supplier, supplier_id, "Supplier")


def create_supplier(db: Session, data: SupplierCreate, actor: User, request: Request | None = None):
    if data.user_id is not None:
        linked_user = db.query(User).filter(User.id == data.user_id).first()
        if not linked_user or linked_user.user_type != "SUPPLIER":
            raise HTTPException(status_code=400, detail="user_id must reference an existing SUPPLIER account")
        already_linked = db.query(Supplier).filter(Supplier.user_id == data.user_id).first()
        if already_linked:
            raise HTTPException(status_code=409, detail="This user is already linked to another supplier")
    item = Supplier(**data.model_dump())
    db.add(item)
    db.flush()
    item.supplier_code = code_for("TVA-SUP", item.id)
    log_audit(db, actor=actor, action="create_supplier", entity_type="supplier", entity_id=item.id, new_values=serialize_supplier(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def update_supplier(db: Session, supplier_id: int, data: SupplierUpdate, actor: User, request: Request | None = None):
    item = get_supplier(db, supplier_id)
    old = serialize_supplier(item)
    
    update_data = data.model_dump(exclude_unset=True)
    contact_data = update_data.pop("contact", None)
    business_data = update_data.pop("business_info", None)
    invoicing_data = update_data.pop("invoicing", None)
    
    for key, value in update_data.items():
        setattr(item, key, value)
        
    if contact_data:
        if not item.contacts:
            from app.models.suppliers import SupplierContact
            new_contact = SupplierContact(supplier_id=item.id, is_primary=True)
            db.add(new_contact)
            item.contacts.append(new_contact)
        # contact_data only contains keys the caller explicitly set (see
        # model_dump(exclude_unset=True) above), so an explicit null here is
        # intentional and must be applied, not skipped.
        for k, v in contact_data.items():
            setattr(item.contacts[0], k, v)

    if business_data:
        if not item.business_info:
            from app.models.suppliers import SupplierBusinessInfo
            item.business_info = SupplierBusinessInfo(supplier_id=item.id)
            db.add(item.business_info)
        for k, v in business_data.items():
            setattr(item.business_info, k, v)

    if invoicing_data:
        if not item.invoicing:
            from app.models.suppliers import SupplierInvoicing
            item.invoicing = SupplierInvoicing(supplier_id=item.id)
            db.add(item.invoicing)
        for k, v in invoicing_data.items():
            setattr(item.invoicing, k, v)
                
    log_audit(db, actor=actor, action="update_supplier", entity_type="supplier", entity_id=item.id, old_values=old, new_values=serialize_supplier(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def approve_supplier(db: Session, supplier_id: int, actor: User, request: Request | None = None):
    item = get_supplier(db, supplier_id)
    if not item.user or item.user.user_type != "SUPPLIER":
        raise HTTPException(status_code=400, detail="Supplier account is invalid")
    if not item.user.email_verified:
        raise HTTPException(status_code=409, detail="Supplier email must be verified before approval")
    if item.user.account_status != "ACTIVE" or not item.user.is_active:
        raise HTTPException(status_code=409, detail="Supplier account must be active before approval")
    if (item.approval_status or "").upper() == "APPROVED":
        raise HTTPException(status_code=409, detail="Supplier is already approved")

    old = serialize_supplier(item)
    previous_status = item.approval_status
    now = datetime.utcnow()
    item.approval_status = "APPROVED"
    item.status = "active"
    item.approved_at = now
    item.approved_by = actor.id
    item.rejection_reason = None
    item.pending_requirements = None
    item.user.approval_status = "APPROVED"
    item.user.admin_verified = True
    item.user.admin_verified_at = now
    item.user.admin_verified_by = actor.id
    db.add(SupplierApprovalHistory(
        supplier_id=item.id,
        from_status=previous_status,
        to_status="APPROVED",
        notes="Supplier operational access approved",
        changed_by=actor.id,
    ))
    log_audit(
        db,
        actor=actor,
        action="approve_supplier",
        entity_type="supplier",
        entity_id=item.id,
        old_values=old,
        new_values=serialize_supplier(item),
        request=request,
    )
    try:
        from app.utils.notification_triggers import notify_supplier_approved
        notify_supplier_approved(
            db,
            supplier_id=item.id,
            supplier_name=item.supplier_name,
            user_id=item.user_id,
        )
    except Exception:
        pass
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def reject_supplier(db: Session, supplier_id: int, data: RejectRequest, actor: User, request: Request | None = None):
    # Legacy compatibility: the corrected status model has no terminal
    # supplier "rejected" approval state. Route old rejection requests through
    # the actionable information-required state instead.
    return partial_approve_supplier(
        db,
        supplier_id,
        PartialApprovalRequest(
            admin_comments=data.admin_comments,
            pending_requirements=data.rejection_reason,
        ),
        actor,
        request,
    )


def partial_approve_supplier(db: Session, supplier_id: int, data: PartialApprovalRequest, actor: User, request: Request | None = None):
    item = get_supplier(db, supplier_id)
    old = serialize_supplier(item)
    previous_status = item.approval_status
    item.approval_status = "MORE_INFORMATION_REQUIRED"
    item.admin_comments = data.admin_comments
    item.pending_requirements = data.pending_requirements
    if item.user:
        item.user.approval_status = "MORE_INFORMATION_REQUIRED"
    db.add(SupplierApprovalHistory(
        supplier_id=item.id,
        from_status=previous_status,
        to_status="MORE_INFORMATION_REQUIRED",
        notes=data.pending_requirements or data.admin_comments,
        changed_by=actor.id,
    ))
    log_audit(db, actor=actor, action="request_supplier_information", entity_type="supplier", entity_id=item.id, old_values=old, new_values=serialize_supplier(item), request=request)
    try:
        from app.utils.notification_triggers import notify_supplier_reupload_requested
        notify_supplier_reupload_requested(db, supplier_id=item.id, supplier_name=item.supplier_name, requirements=data.pending_requirements, user_id=item.user_id)
    except Exception:
        pass
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def set_supplier_account_status(
    db: Session,
    supplier_id: int,
    account_status: str,
    actor: User,
    *,
    reason: str = "",
    request: Request | None = None,
):
    item = get_supplier(db, supplier_id)
    if not item.user or item.user.user_type != "SUPPLIER":
        raise HTTPException(status_code=400, detail="Supplier account is invalid")
    old_status = item.user.account_status
    normalized = account_status.upper()
    item.user.account_status = normalized
    item.user.is_active = normalized == "ACTIVE"
    item.status = "active" if normalized == "ACTIVE" else normalized.lower()
    if normalized in {"INACTIVE", "SUSPENDED", "LOCKED"}:
        item.user.deactivated_at = datetime.utcnow()
        item.user.deactivated_by = actor.id
        item.user.deactivation_reason = reason or normalized.title()
        item.user.token_version += 1
    else:
        item.user.deactivated_at = None
        item.user.deactivated_by = None
        item.user.deactivation_reason = None
    from app.models.users import UserStatusHistory
    db.add(UserStatusHistory(
        user_id=item.user.id,
        from_status=old_status,
        to_status=normalized,
        reason=reason or f"Supplier account {normalized.lower()}",
        changed_by=actor.id,
    ))
    log_audit(
        db,
        actor=actor,
        action=f"{normalized.lower()}_supplier",
        entity_type="supplier",
        entity_id=item.id,
        old_values={"account_status": old_status},
        new_values={"account_status": normalized},
        request=request,
    )
    try:
        from app.utils.notification_triggers import notify_supplier_account_status
        notify_supplier_account_status(
            db,
            supplier_id=item.id,
            supplier_name=item.supplier_name,
            account_status=normalized,
            reason=reason,
            user_id=item.user_id,
        )
    except Exception:
        pass
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def update_supplier_markup(db: Session, supplier_id: int, data: SupplierMarkupRequest, actor: User, request: Request | None = None):
    # This is the ONLY place a supplier's live markup_type/markup_value may
    # change -- self-service requests (request_supplier_commission below)
    # only ever write to the commission_request_* staging fields.
    item = get_supplier(db, supplier_id)
    old = serialize_supplier(item)
    item.markup_type = data.markup_type
    item.markup_value = data.markup_value
    commission_request_pending = item.commission_request_status == "pending"
    if commission_request_pending:
        item.commission_request_status = "approved"
        item.commission_reviewed_at = datetime.utcnow()
        item.pending_requirements = None
        try:
            from app.utils.notification_triggers import notify_supplier_commission_approved
            notify_supplier_commission_approved(db, supplier_id=item.id, supplier_name=item.supplier_name, markup_type=data.markup_type, markup_value=data.markup_value, user_id=item.user_id)
        except Exception:
            pass
    log_audit(db, actor=actor, action="update_supplier_markup", entity_type="supplier", entity_id=item.id, old_values=old, new_values=serialize_supplier(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def request_supplier_commission(db: Session, user: User, data: SupplierMarkupRequest, request: Request | None = None):
    # Self-service: a supplier may only STAGE a commission request here.
    # The live markup_type/markup_value fields are only ever changed by an
    # admin via update_supplier_markup above -- this function must never
    # touch them, or a supplier could set their own commission unreviewed.
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    if supplier.commission_request_status == "pending":
        raise HTTPException(status_code=400, detail="A commission request is already pending")
    old = serialize_supplier(supplier)
    supplier.commission_request_type = data.markup_type
    supplier.commission_request_value = data.markup_value
    supplier.commission_request_status = "pending"
    supplier.commission_requested_at = datetime.utcnow()
    supplier.commission_reviewed_at = None
    supplier.pending_requirements = "Commission request pending admin approval"
    log_audit(db, actor=user, action="request_supplier_commission", entity_type="supplier", entity_id=supplier.id, old_values=old, new_values=serialize_supplier(supplier), request=request)
    try:
        from app.utils.notification_triggers import notify_supplier_commission_requested
        notify_supplier_commission_requested(db, supplier_id=supplier.id, supplier_name=supplier.supplier_name, markup_type=data.markup_type, markup_value=data.markup_value, user_id=user.id)
    except Exception:
        pass
    db.commit()
    db.refresh(supplier)
    return serialize_supplier(supplier)


def _submit_supplier_verification(db: Session, supplier: Supplier, actor: User, request: Request | None = None):
    old = serialize_supplier(supplier)
    supplier.approval_status = "PENDING"
    supplier.status = "active"
    supplier.rejection_reason = None
    supplier.pending_requirements = None
    log_audit(db, actor=actor, action="submit_supplier_verification", entity_type="supplier", entity_id=supplier.id, old_values=old, new_values=serialize_supplier(supplier), request=request)
    db.commit()
    db.refresh(supplier)
    try:
        from app.utils.notification_triggers import notify_supplier_submitted_verification
        notify_supplier_submitted_verification(db, supplier_id=supplier.id, supplier_name=supplier.supplier_name, user_id=supplier.user_id)
        db.commit()
    except Exception:
        pass
    return serialize_supplier(supplier)


def submit_supplier_verification(db: Session, user: User, request: Request | None = None):
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    return _submit_supplier_verification(db, supplier, user, request)


def submit_supplier_verification_for(db: Session, supplier_id: int, actor: User, request: Request | None = None):
    supplier = get_supplier(db, supplier_id)
    if supplier.user_id != actor.id:
        from app.auth.permissions import expand_permission_slugs, get_user_role_ids
        from app.models.permissions import Permission, RolePermission

        role_ids = get_user_role_ids(actor)
        allowed_slugs = expand_permission_slugs(("suppliers.edit", "update-suppliers"))
        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.slug.in_(allowed_slugs))
            .filter(Permission.is_active == True)
            .first()
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")
    return _submit_supplier_verification(db, supplier, actor, request)


def review_supplier_document(db: Session, supplier_id: int, document_id: int, data: DocumentReviewRequest, actor: User, request: Request | None = None):
    document = (
        db.query(SupplierDocument)
        .filter(SupplierDocument.id == document_id, SupplierDocument.supplier_id == supplier_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    old = _document(document)
    document.status = data.status
    document.rejection_reason = data.rejection_reason if data.status == "rejected" else None
    document.reviewed_at = datetime.utcnow()
    document.reviewed_by = actor.id

    log_audit(
        db,
        actor=actor,
        action=f"{data.status}_supplier_document",
        entity_type="supplier_document",
        entity_id=document.id,
        old_values=old,
        new_values=_document(document),
        request=request,
    )
    db.commit()
    db.refresh(document)
    return _document(document)


def review_supplier_vehicle(db: Session, supplier_id: int, vehicle_id: int, data: VehicleReviewRequest, actor: User, request: Request | None = None):
    vehicle = (
        db.query(SupplierVehicle)
        .filter(SupplierVehicle.id == vehicle_id, SupplierVehicle.supplier_id == supplier_id)
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    old = {"id": vehicle.id, "approval_status": vehicle.approval_status, "rejection_reason": vehicle.rejection_reason}
    vehicle.approval_status = data.approval_status
    vehicle.rejection_reason = data.rejection_reason if data.approval_status == "rejected" else None
    vehicle.reviewed_at = datetime.utcnow()
    vehicle.reviewed_by = actor.id

    log_audit(
        db,
        actor=actor,
        action=f"{data.approval_status}_supplier_vehicle",
        entity_type="supplier_vehicle",
        entity_id=vehicle.id,
        old_values=old,
        new_values={"id": vehicle.id, "approval_status": vehicle.approval_status, "rejection_reason": vehicle.rejection_reason},
        request=request,
    )
    db.commit()
    db.refresh(vehicle)
    return _serialize_vehicle(vehicle)
