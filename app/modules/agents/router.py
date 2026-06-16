from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.agents.schemas import AgentCreate, AgentDiscountRequest, AgentUpdate
from app.modules.agents.service import approve_agent, create_agent, get_agent, list_agents, partial_approve_agent, reject_agent, serialize_agent, update_agent, update_agent_discount
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.operations import PartialApprovalRequest, RejectRequest
from app.modules.users.models import User

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
@router.get("/")
def agents(params: dict = Depends(pagination_params), country_id: str = Query(default=""), status: str = Query(default=""), approval_status: str = Query(default=""), start_date: str = Query(default=""), end_date: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("agents.view", "view-agents"))):
    return {"status": "success", **list_agents(db, params["page"], params["limit"], params["search"], country_id, status, approval_status, start_date, end_date)}


@router.post("/")
def add_agent(data: AgentCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.create", "create-agents"))):
    return {"status": "success", "message": "Agent created successfully", "data": create_agent(db, data, current_user, request)}


@router.get("/{agent_id}")
def agent_detail(agent_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("agents.view", "view-agents"))):
    return {"status": "success", "data": serialize_agent(get_agent(db, agent_id))}


@router.put("/{agent_id}")
def edit_agent(agent_id: int, data: AgentUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.edit", "update-agents"))):
    return {"status": "success", "message": "Agent updated successfully", "data": update_agent(db, agent_id, data, current_user, request)}


@router.patch("/{agent_id}/approve")
def approve(agent_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.approve"))):
    return {"status": "success", "message": "Agent approved successfully", "data": approve_agent(db, agent_id, current_user, request)}


@router.patch("/{agent_id}/reject")
def reject(agent_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.reject"))):
    return {"status": "success", "message": "Agent rejected successfully", "data": reject_agent(db, agent_id, data, current_user, request)}


@router.patch("/{agent_id}/partial-approve")
def partial_approve(agent_id: int, data: PartialApprovalRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.partial_approve", "agents.approve"))):
    return {"status": "success", "message": "Agent partially approved successfully", "data": partial_approve_agent(db, agent_id, data, current_user, request)}


@router.patch("/{agent_id}/discount")
def discount(agent_id: int, data: AgentDiscountRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("agents.manage_discount"))):
    return {"status": "success", "message": "Agent discount updated successfully", "data": update_agent_discount(db, agent_id, data, current_user, request)}
