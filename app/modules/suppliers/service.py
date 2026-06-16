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
    return {key: getattr(item, key) for key in ["id", "document_type", "document_name", "file_path", "file_size", "mime_type", "status", "rejection_reason", "uploaded_at", "reviewed_at", "reviewed_by"]}


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
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
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
