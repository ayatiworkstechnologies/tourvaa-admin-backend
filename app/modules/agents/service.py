from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.agents.models import Agent, AgentBusinessInfo, AgentContact, AgentInvoicing
from app.modules.agents.schemas import AgentCreate, AgentDiscountRequest, AgentUpdate
from app.modules.operations import PartialApprovalRequest, RejectRequest, approve_item, code_for, filter_review_query, get_or_404, partial_approve_item, reject_item, relationship_list, serialize_common_review, simple_paginate
from app.modules.users.models import User


def _contact(item):
    return {key: getattr(item, key) for key in ["id", "contact_name", "designation", "phone", "email", "alternate_phone", "is_primary", "created_at", "updated_at"]}


def _document(item):
    file_path = item.file_path or ""
    file_url = file_path
    if file_path and not file_path.startswith("http"):
        file_url = file_path if file_path.startswith("/") else "/storage/" + file_path
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


def serialize_agent(item: Agent):
    data = serialize_common_review(item, "agent_name", "agent_code")
    data.update({
        "agent_type": item.agent_type,
        "discount_type": item.discount_type,
        "discount_value": item.discount_value,
        "contacts": relationship_list(item.contacts, _contact),
        "documents": relationship_list(item.documents, _document),
        "business_info": {
            "years_in_business": item.business_info.years_in_business,
            "certificate_of_incorporation": item.business_info.certificate_of_incorporation,
            "monthly_customers_count": item.business_info.monthly_customers_count,
            "target_market": item.business_info.target_market,
            "destinations_sold": item.business_info.destinations_sold,
            "iata_registration_number": item.business_info.iata_registration_number,
            "gst_tax_number": item.business_info.gst_tax_number,
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
    })
    return data


def list_agents(db: Session, page: int, limit: int, search: str = "", country_id: str = "", status: str = "", approval_status: str = "", start_date: str = "", end_date: str = ""):
    return simple_paginate(filter_review_query(db.query(Agent), Agent, search=search, country_id=country_id, status=status, approval_status=approval_status, start_date=start_date, end_date=end_date, name_field="agent_name"), page, limit, serialize_agent)


def get_agent(db: Session, agent_id: int):
    return get_or_404(db, Agent, agent_id, "Agent")


def create_agent(db: Session, data: AgentCreate, actor: User, request: Request | None = None):
    item = Agent(**data.model_dump())
    db.add(item)
    db.flush()
    item.agent_code = code_for("TVA-AGT", item.id)
    log_audit(db, actor=actor, action="create_agent", entity_type="agent", entity_id=item.id, new_values=serialize_agent(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_agent(item)


def update_agent(db: Session, agent_id: int, data: AgentUpdate, actor: User, request: Request | None = None):
    item = get_agent(db, agent_id)
    old = serialize_agent(item)
    update_data = data.model_dump(exclude_unset=True)
    contact_data = update_data.pop("contact", None)
    business_data = update_data.pop("business_info", None)
    invoicing_data = update_data.pop("invoicing", None)

    for key, value in update_data.items():
        setattr(item, key, value)

    if contact_data:
        primary = item.contacts[0] if item.contacts else None
        if not primary:
            primary = AgentContact(agent_id=item.id, is_primary=True)
            db.add(primary)
            item.contacts.append(primary)
        for key, value in contact_data.items():
            if value is not None:
                setattr(primary, key, value)

    if business_data:
        if not item.business_info:
            item.business_info = AgentBusinessInfo(agent_id=item.id)
            db.add(item.business_info)
        for key, value in business_data.items():
            if value is not None:
                setattr(item.business_info, key, value)

    if invoicing_data:
        if not item.invoicing:
            item.invoicing = AgentInvoicing(agent_id=item.id)
            db.add(item.invoicing)
        for key, value in invoicing_data.items():
            if value is not None:
                setattr(item.invoicing, key, value)

    log_audit(db, actor=actor, action="update_agent", entity_type="agent", entity_id=item.id, old_values=old, new_values=serialize_agent(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_agent(item)


def approve_agent(db: Session, agent_id: int, actor: User, request: Request | None = None):
    return approve_item(db, get_agent(db, agent_id), actor, "agent", serialize_agent, request)


def reject_agent(db: Session, agent_id: int, data: RejectRequest, actor: User, request: Request | None = None):
    return reject_item(db, get_agent(db, agent_id), data, actor, "agent", serialize_agent, request)


def partial_approve_agent(db: Session, agent_id: int, data: PartialApprovalRequest, actor: User, request: Request | None = None):
    return partial_approve_item(db, get_agent(db, agent_id), data, actor, "agent", serialize_agent, request)


def update_agent_discount(db: Session, agent_id: int, data: AgentDiscountRequest, actor: User, request: Request | None = None):
    item = get_agent(db, agent_id)
    old = serialize_agent(item)
    item.discount_type = data.discount_type
    item.discount_value = data.discount_value
    log_audit(db, actor=actor, action="update_agent_discount", entity_type="agent", entity_id=item.id, old_values=old, new_values=serialize_agent(item), request=request)
    db.commit()
    db.refresh(item)
    return serialize_agent(item)


def submit_agent_verification(db: Session, user: User, request: Request | None = None):
    agent = db.query(Agent).filter(Agent.user_id == user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    old = serialize_agent(agent)
    agent.approval_status = "admin_review_pending"
    agent.status = "inactive"
    agent.rejection_reason = None
    agent.pending_requirements = None
    log_audit(db, actor=user, action="submit_agent_verification", entity_type="agent", entity_id=agent.id, old_values=old, new_values=serialize_agent(agent), request=request)
    try:
        from app.modules.common.notification_triggers import notify_agent_submitted_verification
        notify_agent_submitted_verification(db, agent_id=agent.id, agent_name=agent.agent_name, user_id=user.id)
    except Exception:
        pass
    db.commit()
    db.refresh(agent)
    return serialize_agent(agent)
