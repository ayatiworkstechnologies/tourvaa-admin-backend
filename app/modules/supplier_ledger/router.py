from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.supplier_ledger import service
from app.modules.supplier_ledger.schemas import SupplierPayoutCreate, SupplierPayoutMarkPaid

router = APIRouter(tags=["Supplier Ledger"])


@router.get("/supplier-ledgers")
def list_ledgers(pagination=Depends(pagination_params), supplier_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", **service.list_all_ledgers(db, page=pagination["page"], limit=pagination["limit"], supplier_id=supplier_id or None, status=status)}


@router.get("/suppliers/{supplier_id}/ledger")
def supplier_ledger(supplier_id: int, pagination=Depends(pagination_params), status: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", **service.get_supplier_ledger(db, supplier_id=supplier_id, page=pagination["page"], limit=pagination["limit"], status=status)}


@router.get("/supplier-statements/{supplier_id}")
def supplier_statement(supplier_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", "data": service.get_supplier_statement(db, supplier_id=supplier_id)}


@router.get("/supplier-payouts")
def list_payouts(pagination=Depends(pagination_params), supplier_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", **service.list_payouts(db, page=pagination["page"], limit=pagination["limit"], supplier_id=supplier_id or None, status=status)}


@router.post("/supplier-payouts")
def create_payout(data: SupplierPayoutCreate, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("suppliers.approve", "update-suppliers"))):
    result = service.create_payout(db, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Payout created", "data": result}


@router.post("/supplier-payouts/{payout_id}/approve")
def approve_payout(payout_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("suppliers.approve", "update-suppliers"))):
    result = service.approve_payout(db, payout_id=payout_id, actor=current_user, request=request)
    return {"status": "success", "message": "Payout approved", "data": result}


@router.patch("/supplier-payouts/{payout_id}/mark-paid")
def mark_paid(payout_id: int, data: SupplierPayoutMarkPaid, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("suppliers.approve", "update-suppliers"))):
    result = service.mark_payout_paid(db, payout_id=payout_id, data=data, actor=current_user, request=request)
    return {"status": "success", "message": "Payout marked as paid", "data": result}


@router.post("/supplier-payouts/{payout_id}/mark-paid")
def mark_paid_post(payout_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_any_permission("suppliers.approve", "update-suppliers"))):
    result = service.mark_payout_paid(db, payout_id=payout_id, data=SupplierPayoutMarkPaid(), actor=current_user, request=request)
    return {"status": "success", "message": "Payout marked as paid", "data": result}
