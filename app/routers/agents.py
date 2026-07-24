from fastapi import APIRouter, Depends, Query, Request, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agents import Agent
from app.schemas.agents import AgentCreate, AgentDiscountRequest, AgentDocumentReviewRequest, AgentSelfUpdate, AgentUpdate
from app.services.agents import AGENT_DOCUMENT_TYPES, approve_agent, create_agent, get_agent, list_agents, partial_approve_agent, reject_agent, request_agent_commission, review_agent_document, serialize_agent, submit_agent_verification, update_agent, update_agent_discount
from app.schemas.auth import UnifiedRegisterSchema, VerifyEmailSchema
from app.services.auth import register_unified_user, verify_email
from app.auth.permissions import get_current_user, require_any_permission, get_user_role_ids, expand_permission_slugs
from app.utils.pagination import pagination_params
from app.utils.operations import PartialApprovalRequest, RejectRequest
from app.models.permissions import Permission, RolePermission
from app.models.users import User

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post("/register")
def register_agent(data: UnifiedRegisterSchema, db: Session = Depends(get_db)):
    if data.account_type != "AGENT":
        raise HTTPException(status_code=422, detail="account_type must be AGENT")
    user = register_unified_user(db, data)
    return {"status": "success", "message": "Verification email sent", "data": {"id": user.id, "email": user.email, "approval_status": user.approval_status, "verification_required": True}}


@router.post("/verify-email")
def verify_agent_email(data: VerifyEmailSchema, db: Session = Depends(get_db)):
    verify_email(db, data.token)
    return {"status": "success", "message": "Agent email verified successfully"}


@router.post("/submit-verification")
def submit_verification(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "message": "Agent verification submitted", "data": submit_agent_verification(db, current_user, request)}


@router.get("/pending")
def pending_agents(params: dict = Depends(pagination_params), db: Session = Depends(get_db), _=Depends(require_any_permission("agents.view", "view-agents"))):
    return {"status": "success", **list_agents(db, params["page"], params["limit"], params["search"], approval_status="admin_review_pending")}


@router.get("")
@router.get("/")
def agents(
    params: dict = Depends(pagination_params),
    country_id: str = Query(default=""),
    status: str = Query(default=""),
    approval_status: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("agents.view", "view-agents")),
):
    return {"status": "success", **list_agents(db, params["page"], params["limit"], params["search"], country_id, status, approval_status, start_date, end_date)}


@router.post("/")
def add_agent(data: AgentCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.create", "create-agents"))):
    return {"status": "success", "message": "Agent created successfully", "data": create_agent(db, data, current_user, request)}


@router.get("/me")
def my_agent(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return {"status": "success", "data": serialize_agent(agent)}


@router.get("/document-requirements")
def document_requirements(_current_user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "data": [
            {"document_type": key, **metadata}
            for key, metadata in AGENT_DOCUMENT_TYPES.items()
        ],
    }


@router.put("/me")
@router.patch("/me")
def edit_my_agent(data: AgentSelfUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    safe_update = AgentUpdate(**data.model_dump(exclude_unset=True))
    return {"status": "success", "message": "Agent updated successfully", "data": update_agent(db, agent.id, safe_update, current_user, request)}


@router.post("/me/commission-request")
def request_my_commission(data: AgentDiscountRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "message": "Commission request submitted for admin approval", "data": request_agent_commission(db, current_user, data, request)}


@router.get("/{agent_id}")
def agent_detail(agent_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = get_agent(db, agent_id)
    if agent.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("agents.view", "view-agents"))
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

    return {"status": "success", "data": serialize_agent(agent)}


@router.put("/{agent_id}")
@router.patch("/{agent_id}")
def edit_agent(agent_id: int, data: AgentUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = get_agent(db, agent_id)
    if agent.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("agents.edit", "update-agents"))
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
    return {"status": "success", "message": "Agent updated successfully", "data": update_agent(db, agent_id, data, current_user, request)}


@router.get("/{agent_id}/documents")
def get_agent_documents(agent_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = get_agent(db, agent_id)
    if agent.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("agents.view", "view-agents"))
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

    from app.models.agents import AgentDocument
    from app.services.agents import _document
    docs = db.query(AgentDocument).filter(AgentDocument.agent_id == agent_id).all()
    return {"status": "success", "data": [_document(doc) for doc in docs]}


@router.post("/{agent_id}/documents")
async def upload_agent_document(
    agent_id: int,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = get_agent(db, agent_id)
    if agent.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("agents.edit", "update-agents"))
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

    document_type = document_type.strip().lower()
    if document_type not in AGENT_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid agent document type")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is required")

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File must be 10MB or smaller")

    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/avif": "avif",
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    }
    extension = allowed_types.get(file.content_type or "")
    if not extension:
        filename_lower = file.filename.lower()
        if filename_lower.endswith(".pdf"):
            extension = "pdf"
        elif filename_lower.endswith(".jpg") or filename_lower.endswith(".jpeg"):
            extension = "jpg"
        elif filename_lower.endswith(".png"):
            extension = "png"
        elif filename_lower.endswith(".webp"):
            extension = "webp"
        elif filename_lower.endswith(".avif"):
            extension = "avif"
        elif filename_lower.endswith(".doc"):
            extension = "doc"
        elif filename_lower.endswith(".docx"):
            extension = "docx"
        else:
            raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, AVIF, PDF, DOC, and DOCX files are allowed")

    from uuid import uuid4
    from app.utils.imagekit_client import upload_to_imagekit
    from app.models.agents import AgentDocument
    from app.services.agents import _document

    filename = f"{uuid4().hex}.{extension}"
    uploaded = upload_to_imagekit(content, filename, folder="/tourvaa/agent-documents", is_private=True)
    relative_path = f"imagekit:{uploaded['file_path']}"

    existing_doc = db.query(AgentDocument).filter(
        AgentDocument.agent_id == agent_id,
        AgentDocument.document_type == document_type
    ).first()

    if existing_doc:
        existing_doc.file_path = relative_path
        existing_doc.document_name = file.filename
        existing_doc.file_size = len(content)
        existing_doc.mime_type = file.content_type or "application/octet-stream"
        existing_doc.status = "pending"
        existing_doc.rejection_reason = None
        existing_doc.reviewed_at = None
        existing_doc.reviewed_by = None
        if document_type in {key for key, value in AGENT_DOCUMENT_TYPES.items() if value["required"]} and agent.approval_status in {"approved", "approved_live"}:
            agent.approval_status = "documents_pending"
            agent.status = "inactive"
            current_user.approval_status = "documents_pending"
        db.commit()
        db.refresh(existing_doc)
        doc_obj = existing_doc
    else:
        new_doc = AgentDocument(
            agent_id=agent_id,
            document_type=document_type,
            document_name=file.filename,
            file_path=relative_path,
            file_size=len(content),
            mime_type=file.content_type or "application/octet-stream",
            status="pending",
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        doc_obj = new_doc

    return {
        "status": "success",
        "message": "Document uploaded successfully",
        "data": _document(doc_obj)
    }


@router.patch("/{agent_id}/documents/{document_id}/review")
def review_document(
    agent_id: int,
    document_id: int,
    data: AgentDocumentReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("agents.approve", "agents.reject")),
):
    return {
        "status": "success",
        "message": f"Document {data.status} successfully",
        "data": review_agent_document(db, agent_id, document_id, data, current_user, request),
    }


@router.post("/{agent_id}/approve")
@router.patch("/{agent_id}/approve")
def approve(agent_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.approve"))):
    return {"status": "success", "message": "Agent approved successfully", "data": approve_agent(db, agent_id, current_user, request)}


@router.post("/{agent_id}/reject")
@router.patch("/{agent_id}/reject")
def reject(agent_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.reject"))):
    return {"status": "success", "message": "Agent rejected successfully", "data": reject_agent(db, agent_id, data, current_user, request)}


@router.post("/{agent_id}/partial-approve")
@router.patch("/{agent_id}/partial-approve")
def partial_approve(agent_id: int, data: PartialApprovalRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.partial_approve", "agents.approve"))):
    return {"status": "success", "message": "Agent partially approved successfully", "data": partial_approve_agent(db, agent_id, data, current_user, request)}


@router.post("/{agent_id}/request-correction")
def request_correction(agent_id: int, data: PartialApprovalRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.reject", "agents.approve"))):
    return {"status": "success", "message": "Agent correction requested", "data": partial_approve_agent(db, agent_id, data, current_user, request)}


@router.post("/{agent_id}/discount")
@router.patch("/{agent_id}/discount")
def discount(agent_id: int, data: AgentDiscountRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.manage_discount"))):
    return {"status": "success", "message": "Agent discount updated successfully", "data": update_agent_discount(db, agent_id, data, current_user, request)}
