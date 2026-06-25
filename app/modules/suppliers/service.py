from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.operations import (
    PartialApprovalRequest,
    RejectRequest,
    approve_item,
    code_for,
    filter_review_query,
    get_or_404,
    partial_approve_item,
    reject_item,
    relationship_list,
    serialize_common_review,
    simple_paginate,
)
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.schemas import SupplierCreate, SupplierMarkupRequest, SupplierUpdate
from app.modules.users.models import User


def _contact(item):
    return {key: getattr(item, key) for key in ["id", "contact_name", "designation", "phone", "email", "alternate_phone", "is_primary", "created_at", "updated_at"]}


def _document(item):
    file_path = item.file_path or ""
    file_url = file_path
    if file_path and not file_path.startswith("http"):
        if not file_path.startswith("/"):
            file_url = "/storage/" + file_path
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


def serialize_supplier(item: Supplier):
    data = serialize_common_review(item, "supplier_name", "supplier_code")
    data.update(
        {
            "supplier_type": item.supplier_type,
            "markup_type": item.markup_type,
            "markup_value": item.markup_value,
            "contacts": relationship_list(item.contacts, _contact),
            "vehicles": relationship_list(item.vehicles, lambda vehicle: {
                "id": vehicle.id,
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "capacity": vehicle.capacity,
                "fitness_certificate": vehicle.fitness_certificate,
                "insurance_document": vehicle.insurance_document,
                "vehicle_photos": vehicle.vehicle_photos,
                "approval_status": vehicle.approval_status,
            }),
            "documents": relationship_list(item.documents, _document),
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
    query = filter_review_query(db.query(Supplier), Supplier, search=search, country_id=country_id, status=status, approval_status=approval_status, start_date=start_date, end_date=end_date, name_field="supplier_name")
    return simple_paginate(query, page, limit, serialize_supplier)


def get_supplier(db: Session, supplier_id: int):
    return get_or_404(db, Supplier, supplier_id, "Supplier")


def create_supplier(db: Session, data: SupplierCreate, actor: User, request: Request | None = None):
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
            from app.modules.suppliers.models import SupplierContact
            new_contact = SupplierContact(supplier_id=item.id, is_primary=True)
            db.add(new_contact)
            item.contacts.append(new_contact)
        for k, v in contact_data.items():
            if v is not None:
                setattr(item.contacts[0], k, v)
                
    if business_data:
        if not item.business_info:
            from app.modules.suppliers.models import SupplierBusinessInfo
            item.business_info = SupplierBusinessInfo(supplier_id=item.id)
            db.add(item.business_info)
        for k, v in business_data.items():
            if v is not None:
                setattr(item.business_info, k, v)
                
    if invoicing_data:
        if not item.invoicing:
            from app.modules.suppliers.models import SupplierInvoicing
            item.invoicing = SupplierInvoicing(supplier_id=item.id)
            db.add(item.invoicing)
        for k, v in invoicing_data.items():
            if v is not None:
                setattr(item.invoicing, k, v)
                
    log_audit(db, actor=actor, action="update_supplier", entity_type="supplier", entity_id=item.id, old_values=old, new_values=serialize_supplier(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def approve_supplier(db: Session, supplier_id: int, actor: User, request: Request | None = None):
    return approve_item(db, get_supplier(db, supplier_id), actor, "supplier", serialize_supplier, request)


def reject_supplier(db: Session, supplier_id: int, data: RejectRequest, actor: User, request: Request | None = None):
    return reject_item(db, get_supplier(db, supplier_id), data, actor, "supplier", serialize_supplier, request)


def partial_approve_supplier(db: Session, supplier_id: int, data: PartialApprovalRequest, actor: User, request: Request | None = None):
    return partial_approve_item(db, get_supplier(db, supplier_id), data, actor, "supplier", serialize_supplier, request)


def update_supplier_markup(db: Session, supplier_id: int, data: SupplierMarkupRequest, actor: User, request: Request | None = None):
    item = get_supplier(db, supplier_id)
    old = serialize_supplier(item)
    item.markup_type = data.markup_type
    item.markup_value = data.markup_value
    log_audit(db, actor=actor, action="update_supplier_markup", entity_type="supplier", entity_id=item.id, old_values=old, new_values=serialize_supplier(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_supplier(item)


def submit_supplier_verification(db: Session, user: User, request: Request | None = None):
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    old = serialize_supplier(supplier)
    supplier.approval_status = "admin_review_pending"
    supplier.status = "inactive"
    supplier.rejection_reason = None
    supplier.pending_requirements = None
    log_audit(db, actor=user, action="submit_supplier_verification", entity_type="supplier", entity_id=supplier.id, old_values=old, new_values=serialize_supplier(supplier), request=request)
    db.commit()
    db.refresh(supplier)
    try:
        from app.modules.common.notification_triggers import notify_supplier_submitted_verification
        notify_supplier_submitted_verification(db, supplier_id=supplier.id, supplier_name=supplier.supplier_name, user_id=user.id)
        db.commit()
    except Exception:
        pass
    return serialize_supplier(supplier)
