from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.operations import PartialApprovalRequest, RejectRequest
from app.modules.suppliers.schemas import SupplierCreate, SupplierMarkupRequest, SupplierUpdate
from app.modules.suppliers.service import (
    approve_supplier,
    create_supplier,
    get_supplier,
    list_suppliers,
    partial_approve_supplier,
    reject_supplier,
    serialize_supplier,
    update_supplier,
    update_supplier_markup,
)
from app.modules.users.models import User

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.get("")
@router.get("/")
def suppliers(params: dict = Depends(pagination_params), country_id: str = Query(default=""), status: str = Query(default=""), approval_status: str = Query(default=""), start_date: str = Query(default=""), end_date: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", **list_suppliers(db, params["page"], params["limit"], params["search"], country_id, status, approval_status, start_date, end_date)}


@router.post("/")
def add_supplier(data: SupplierCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.create", "create-suppliers"))):
    return {"status": "success", "message": "Supplier created successfully", "data": create_supplier(db, data, current_user, request)}


@router.get("/{supplier_id}")
def supplier_detail(supplier_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", "data": serialize_supplier(get_supplier(db, supplier_id))}


@router.put("/{supplier_id}")
def edit_supplier(supplier_id: int, data: SupplierUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.edit", "update-suppliers"))):
    return {"status": "success", "message": "Supplier updated successfully", "data": update_supplier(db, supplier_id, data, current_user, request)}


@router.patch("/{supplier_id}/approve")
def approve(supplier_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.approve"))):
    return {"status": "success", "message": "Supplier approved successfully", "data": approve_supplier(db, supplier_id, current_user, request)}


@router.patch("/{supplier_id}/reject")
def reject(supplier_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.reject"))):
    return {"status": "success", "message": "Supplier rejected successfully", "data": reject_supplier(db, supplier_id, data, current_user, request)}


@router.patch("/{supplier_id}/partial-approve")
def partial_approve(supplier_id: int, data: PartialApprovalRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.partial_approve", "suppliers.approve"))):
    return {"status": "success", "message": "Supplier partially approved successfully", "data": partial_approve_supplier(db, supplier_id, data, current_user, request)}


@router.patch("/{supplier_id}/markup")
def markup(supplier_id: int, data: SupplierMarkupRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.manage_markup"))):
    return {"status": "success", "message": "Supplier markup updated successfully", "data": update_supplier_markup(db, supplier_id, data, current_user, request)}
