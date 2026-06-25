from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.agents.models import Agent
from app.modules.agents.schemas import AgentCreate, AgentDiscountRequest, AgentUpdate
from app.modules.agents.service import approve_agent, create_agent, get_agent, list_agents, partial_approve_agent, reject_agent, serialize_agent, submit_agent_verification, update_agent, update_agent_discount
from app.modules.auth.schemas import RegisterSchema, VerifyEmailSchema
from app.modules.auth.service import register_user, verify_email
from app.modules.common.auth import get_current_user, require_any_permission, get_user_role_ids, expand_permission_slugs
from app.modules.common.pagination import pagination_params
from app.modules.operations import PartialApprovalRequest, RejectRequest
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User

router = APIRouter(prefix="/agents", tags=["Agents"])


def _registration_with_role(db: Session, data: RegisterSchema, role_slug: str):
    role = db.query(Role).filter(Role.slug == role_slug).filter(Role.is_active == True).first()
    if not role:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Registration role is not available")
    return register_user(db, data.model_copy(update={"role_id": role.id}))


@router.post("/register")
def register_agent(data: RegisterSchema, db: Session = Depends(get_db)):
    user = _registration_with_role(db, data, "agent-reseller")
    try:
        from app.modules.common.notification_triggers import notify_agent_registered
        notify_agent_registered(db, agent_id=0, agent_name=user.name or user.email, user_id=user.id)
        db.commit()
    except Exception:
        pass
    return {"status": "success", "message": "Agent registration received", "data": {"id": user.id, "email": user.email, "approval_status": user.approval_status}}


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
def agents(params: dict = Depends(pagination_params), country_id: str = Query(default=""), status: str = Query(default=""), approval_status: str = Query(default=""), start_date: str = Query(default=""), end_date: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("agents.view", "view-agents"))):
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


@router.put("/me")
@router.patch("/me")
def edit_my_agent(data: AgentUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return {"status": "success", "message": "Agent updated successfully", "data": update_agent(db, agent.id, data, current_user, request)}


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
