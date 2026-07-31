from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.database import get_db
from app.auth.permissions import require_any_permission
from app.utils.pagination import pagination_params
from app.services import agent_ledger as service
from app.schemas.agent_ledger import AgentPayoutCreate, AgentPayoutMarkPaid
from app.services.agent_scope import ensure_agent_account_access, get_actor_agent, is_agent_user

router = APIRouter(tags=["Agent Ledger"])


@router.get("/agent-ledgers")
def list_ledgers(pagination=Depends(pagination_params), agent_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.view", "view-agent_ledger"))):
    own_agent_id = get_actor_agent(db, current_user).id if is_agent_user(current_user) else None
    if own_agent_id and agent_id and agent_id != own_agent_id:
        raise HTTPException(status_code=403, detail="You can only access your own agent account")
    scoped_agent_id = own_agent_id or agent_id
    return {"status": "success", **service.list_all_ledgers(db, page=pagination["page"], limit=pagination["limit"], agent_id=scoped_agent_id or None, status=status)}


@router.get("/agents/{agent_id}/ledger")
def agent_ledger(agent_id: int, pagination=Depends(pagination_params), status: str = Query(default=""), db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.view", "view-agent_ledger"))):
    ensure_agent_account_access(db, agent_id, current_user)
    return {"status": "success", **service.get_agent_ledger(db, agent_id=agent_id, page=pagination["page"], limit=pagination["limit"], status=status)}


@router.get("/agent-statements/{agent_id}")
def agent_statement(agent_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.view", "view-agent_ledger"))):
    ensure_agent_account_access(db, agent_id, current_user)
    return {"status": "success", "data": service.get_agent_statement(db, agent_id=agent_id)}


@router.get("/agent-payouts")
def list_payouts(pagination=Depends(pagination_params), agent_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.view", "view-agent_ledger"))):
    own_agent_id = get_actor_agent(db, current_user).id if is_agent_user(current_user) else None
    if own_agent_id and agent_id and agent_id != own_agent_id:
        raise HTTPException(status_code=403, detail="You can only access your own agent account")
    scoped_agent_id = own_agent_id or agent_id
    return {"status": "success", **service.list_payouts(db, page=pagination["page"], limit=pagination["limit"], agent_id=scoped_agent_id or None, status=status)}


@router.post("/agent-payouts")
def create_payout(
    data: AgentPayoutCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("agent_ledger.create_payout", "create-agent_ledger")),
):
    result = service.create_payout(db, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Payout created", "data": result}


@router.post("/agent-payouts/{payout_id}/approve")
def approve_payout(payout_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.approve", "update-agent_ledger"))):
    result = service.approve_payout(db, payout_id=payout_id, actor=current_user, request=request)
    return {"status": "success", "message": "Payout approved", "data": result}


@router.patch("/agent-payouts/{payout_id}/mark-paid")
def mark_paid(payout_id: int, data: AgentPayoutMarkPaid, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.mark_paid", "update-agent_ledger"))):
    result = service.mark_payout_paid(db, payout_id=payout_id, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Payout marked as paid", "data": result}


@router.post("/agent-payouts/{payout_id}/mark-paid")
def mark_paid_post(payout_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("agent_ledger.mark_paid", "update-agent_ledger"))):
    result = service.mark_payout_paid(db, payout_id=payout_id, data=AgentPayoutMarkPaid(), actor=current_user, request=request)
    return {"status": "success", "message": "Payout marked as paid", "data": result}
