from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.database import get_db
from app.auth.permissions import require_any_permission
from app.utils.pagination import pagination_params
from app.services import supplier_ledger as service
from app.schemas.supplier_ledger import SupplierPayoutCreate, SupplierPayoutMarkPaid
from app.services.supplier_scope import ensure_supplier_account_access, get_actor_supplier, is_supplier_user

router = APIRouter(tags=["Supplier Ledger"])


@router.get("/supplier-ledgers")
def list_ledgers(pagination=Depends(pagination_params), supplier_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.view", "view-supplier_ledger"))):
    own_supplier_id = get_actor_supplier(db, current_user).id if is_supplier_user(current_user) else None
    if own_supplier_id and supplier_id and supplier_id != own_supplier_id:
        raise HTTPException(status_code=403, detail="You can only access your own supplier account")
    scoped_supplier_id = own_supplier_id or supplier_id
    return {"status": "success", **service.list_all_ledgers(db, page=pagination["page"], limit=pagination["limit"], supplier_id=scoped_supplier_id or None, status=status)}

@router.get("/suppliers/{supplier_id}/ledger")
def supplier_ledger(supplier_id: int, pagination=Depends(pagination_params), status: str = Query(default=""), db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.view", "view-supplier_ledger"))):
    ensure_supplier_account_access(db, supplier_id, current_user)
    return {"status": "success", **service.get_supplier_ledger(db, supplier_id=supplier_id, page=pagination["page"], limit=pagination["limit"], status=status)}


@router.get("/supplier-statements/{supplier_id}")
def supplier_statement(supplier_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.view", "view-supplier_ledger"))):
    ensure_supplier_account_access(db, supplier_id, current_user)
    return {"status": "success", "data": service.get_supplier_statement(db, supplier_id=supplier_id)}


@router.get("/supplier-payouts")
def list_payouts(pagination=Depends(pagination_params), supplier_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.view", "view-supplier_ledger"))):
    own_supplier_id = get_actor_supplier(db, current_user).id if is_supplier_user(current_user) else None
    if own_supplier_id and supplier_id and supplier_id != own_supplier_id:
        raise HTTPException(status_code=403, detail="You can only access your own supplier account")
    scoped_supplier_id = own_supplier_id or supplier_id
    return {"status": "success", **service.list_payouts(db, page=pagination["page"], limit=pagination["limit"], supplier_id=scoped_supplier_id or None, status=status)}


@router.post("/supplier-payouts")
def create_payout(
    data: SupplierPayoutCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("supplier_ledger.create_payout", "create-supplier_ledger")),
):
    result = service.create_payout(db, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Payout created", "data": result}


@router.post("/supplier-payouts/{payout_id}/approve")
def approve_payout(payout_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.approve", "update-supplier_ledger"))):
    result = service.approve_payout(db, payout_id=payout_id, actor=current_user, request=request)
    return {"status": "success", "message": "Payout approved", "data": result}


@router.patch("/supplier-payouts/{payout_id}/mark-paid")
def mark_paid(payout_id: int, data: SupplierPayoutMarkPaid, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.mark_paid", "update-supplier_ledger"))):
    result = service.mark_payout_paid(db, payout_id=payout_id, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Payout marked as paid", "data": result}


@router.post("/supplier-payouts/{payout_id}/mark-paid")
def mark_paid_post(payout_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("supplier_ledger.mark_paid", "update-supplier_ledger"))):
    result = service.mark_payout_paid(db, payout_id=payout_id, data=SupplierPayoutMarkPaid(), actor=current_user, request=request)
    return {"status": "success", "message": "Payout marked as paid", "data": result}




