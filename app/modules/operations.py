from datetime import datetime
from math import ceil
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.users.models import User

ACTIVE_STATUSES = {"active", "inactive", "suspended", "blocked"}
APPROVAL_STATUSES = {
    "draft",
    "email_verification_pending",
    "profile_incomplete",
    "documents_pending",
    "admin_review_pending",
    "pending",
    "approved",
    "approved_live",
    "partial_approved",
    "partially_approved",
    "rejected",
    "suspended",
    "blocked",
}
VALUE_TYPES = {"percentage", "fixed"}
DOCUMENT_STATUSES = {"pending", "approved", "rejected", "expired", "reupload_required"}


def _trim(value: str | None):
    return value.strip() if isinstance(value, str) else value


class ApprovalRequest(BaseModel):
    admin_comments: str = Field(default="", max_length=5000)

    @field_validator("admin_comments")
    @classmethod
    def trim_comments(cls, value: str):
        return value.strip()


class RejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=255)
    admin_comments: str = Field(default="", max_length=5000)

    @field_validator("rejection_reason", "admin_comments")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class PartialApprovalRequest(BaseModel):
    admin_comments: str = Field(default="", max_length=5000)
    pending_requirements: str = Field(default="", max_length=5000)

    @field_validator("admin_comments", "pending_requirements")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class ValueSetupRequest(BaseModel):
    value_type: str | None = None
    value: float | None = None
    markup_type: str | None = None
    markup_value: float | None = None
    discount_type: str | None = None
    discount_value: float | None = None

    def resolved(self, type_field: str, value_field: str):
        selected_type = getattr(self, type_field) or self.value_type
        selected_value = getattr(self, value_field)
        if selected_value is None:
            selected_value = self.value
        selected_type = (selected_type or "").strip().lower()
        if selected_type not in VALUE_TYPES:
            raise ValueError("Invalid value type")
        if selected_value is None or selected_value < 0:
            raise ValueError("Value must be zero or greater")
        return selected_type, selected_value


def code_for(prefix: str, item_id: int):
    return f"{prefix}-{item_id:05d}"


def simple_paginate(query, page: int, limit: int, serializer):
    total = query.count()
    rows = query.offset((page - 1) * limit).limit(limit).all()
    items = [serializer(row) for row in rows]
    return {
        "items": items,
        "data": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)),
    }


def relationship_list(items, serializer):
    return [serializer(item) for item in items or []]


def serialize_common_review(item: Any, name_field: str, code_field: str):
    country = getattr(item, "country", None)
    city = getattr(item, "city", None)
    return {
        "id": item.id,
        "user_id": getattr(item, "user_id", None),
        code_field: getattr(item, code_field),
        "code": getattr(item, code_field),
        "name": getattr(item, name_field),
        name_field: getattr(item, name_field),
        "type": getattr(item, name_field.replace("_name", "_type"), ""),
        "country_id": getattr(item, "country_id", None),
        "city_id": getattr(item, "city_id", None),
        "country_name": country.country_name if country else "",
        "city_name": city.city_name if city else "",
        "years_in_operation": getattr(item, "years_in_operation", 0),
        "status": item.status,
        "approval_status": item.approval_status,
        "rejection_reason": item.rejection_reason,
        "admin_comments": item.admin_comments,
        "pending_requirements": getattr(item, "pending_requirements", ""),
        "approved_at": item.approved_at,
        "approved_by": item.approved_by,
        "rejected_at": item.rejected_at,
        "rejected_by": item.rejected_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "total_bookings": 0,
        "completed_bookings": 0,
        "cancelled_bookings": 0,
        "upcoming_bookings": 0,
        "number_of_tours": 0,
        "completed_tours": 0,
        "cancelled_tours": 0,
        "upcoming_tours": 0,
    }


def filter_review_query(query, model, *, search="", country_id="", status="", approval_status="", start_date="", end_date="", name_field=""):
    if search:
        pattern = f"%{search.strip()}%"
        search_columns = [getattr(model, name_field)]
        code_name = name_field.replace("_name", "_code")
        if hasattr(model, code_name):
            search_columns.append(getattr(model, code_name))
        query = query.filter(or_(*[column.ilike(pattern) for column in search_columns]))
    if country_id:
        query = query.filter(model.country_id == int(country_id))
    if status:
        query = query.filter(model.status == status.strip().lower())
    if approval_status:
        query = query.filter(model.approval_status == approval_status.strip().lower())
    if start_date:
        query = query.filter(model.created_at >= start_date)
    if end_date:
        query = query.filter(model.created_at <= f"{end_date} 23:59:59")
    return query.order_by(model.id.desc())


def get_or_404(db: Session, model, item_id: int, label: str):
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return item


def _entity_user_id(item) -> int | None:
    """Best-effort: extract the linked user ID from a supplier/agent/affiliate row."""
    return getattr(item, "user_id", None)


def _entity_name(item) -> str:
    for field in ("supplier_name", "agent_name", "affiliate_name", "name"):
        val = getattr(item, field, None)
        if val:
            return val
    return f"#{item.id}"


def approve_item(db: Session, item, actor: User, entity_type: str, serializer, request: Request | None = None):
    old = serializer(item)
    item.approval_status = "approved"
    item.status = "active"
    item.approved_at = datetime.utcnow()
    item.approved_by = actor.id
    item.rejection_reason = None
    
    user_id = _entity_user_id(item)
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.approval_status = "approved"
            user.is_active = True
            
    log_audit(db, actor=actor, action=f"approve_{entity_type}", entity_type=entity_type, entity_id=item.id, old_values=old, new_values=serializer(item), request=request)
    # Notifications
    try:
        from app.modules.common.notification_triggers import notify_supplier_approved, notify_agent_approved
        user_id = _entity_user_id(item)
        name = _entity_name(item)
        if entity_type == "supplier":
            notify_supplier_approved(db, supplier_id=item.id, supplier_name=name, user_id=user_id)
        elif entity_type == "agent":
            notify_agent_approved(db, agent_id=item.id, agent_name=name, user_id=user_id)
    except Exception:
        pass
    db.commit()
    db.refresh(item)
    return serializer(item)


def reject_item(db: Session, item, data: RejectRequest, actor: User, entity_type: str, serializer, request: Request | None = None):
    old = serializer(item)
    item.approval_status = "rejected"
    item.status = "inactive"
    item.rejection_reason = data.rejection_reason
    item.admin_comments = data.admin_comments
    item.rejected_at = datetime.utcnow()
    item.rejected_by = actor.id
    
    user_id = _entity_user_id(item)
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.approval_status = "rejected"
            
    log_audit(db, actor=actor, action=f"reject_{entity_type}", entity_type=entity_type, entity_id=item.id, old_values=old, new_values=serializer(item), request=request)
    # Notifications
    try:
        from app.modules.common.notification_triggers import notify_supplier_rejected, notify_agent_rejected
        user_id = _entity_user_id(item)
        name = _entity_name(item)
        reason = getattr(data, "rejection_reason", "")
        if entity_type == "supplier":
            notify_supplier_rejected(db, supplier_id=item.id, supplier_name=name, rejection_reason=reason, user_id=user_id)
        elif entity_type == "agent":
            notify_agent_rejected(db, agent_id=item.id, agent_name=name, rejection_reason=reason, user_id=user_id)
    except Exception:
        pass
    db.commit()
    db.refresh(item)
    return serializer(item)


def partial_approve_item(db: Session, item, data: PartialApprovalRequest, actor: User, entity_type: str, serializer, request: Request | None = None):
    old = serializer(item)
    item.approval_status = "partial_approved"
    item.admin_comments = data.admin_comments
    item.pending_requirements = data.pending_requirements
    
    user_id = _entity_user_id(item)
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.approval_status = "partial_approved"
            
    log_audit(db, actor=actor, action=f"partial_approve_{entity_type}", entity_type=entity_type, entity_id=item.id, old_values=old, new_values=serializer(item), request=request)
    # Notify supplier of partial approval with pending requirements
    try:
        from app.modules.common.notification_triggers import notify_supplier_reupload_requested, notify_agent_changes_requested
        user_id = _entity_user_id(item)
        name = _entity_name(item)
        if entity_type == "supplier":
            notify_supplier_reupload_requested(db, supplier_id=item.id, supplier_name=name, requirements=data.pending_requirements, user_id=user_id)
        elif entity_type == "agent":
            notify_agent_changes_requested(db, agent_id=item.id, agent_name=name, requirements=data.pending_requirements, user_id=user_id)
    except Exception:
        pass
    db.commit()
    db.refresh(item)
    return serializer(item)

