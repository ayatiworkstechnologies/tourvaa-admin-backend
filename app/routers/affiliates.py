from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.affiliates import AffiliateApiLinkRequest, AffiliateCreate, AffiliateUpdate
from app.services.affiliates import approve_affiliate, create_affiliate, get_affiliate, list_affiliates, reject_affiliate, serialize_affiliate, update_affiliate, update_affiliate_api_link
from app.auth.permissions import require_any_permission
from app.utils.pagination import pagination_params
from app.utils.operations import RejectRequest
from app.models.users import User

router = APIRouter(prefix="/affiliates", tags=["Affiliates"])


@router.get("")
@router.get("/")
def affiliates(
    params: dict = Depends(pagination_params),
    country_id: str = Query(default=""),
    status: str = Query(default=""),
    approval_status: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("affiliates.view")),
):
    return {"status": "success", **list_affiliates(db, params["page"], params["limit"], params["search"], country_id, status, approval_status)}


@router.post("/")
def add_affiliate(data: AffiliateCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.create", "affiliates.approve"))):
    return {"status": "success", "message": "Affiliate created successfully", "data": create_affiliate(db, data, current_user, request)}


@router.get("/{affiliate_id}")
def affiliate_detail(affiliate_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view"))):
    return {"status": "success", "data": serialize_affiliate(get_affiliate(db, affiliate_id))}


@router.put("/{affiliate_id}")
def edit_affiliate(affiliate_id: int, data: AffiliateUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.approve"))):
    return {"status": "success", "message": "Affiliate updated successfully", "data": update_affiliate(db, affiliate_id, data, current_user, request)}


@router.patch("/{affiliate_id}/approve")
def approve(affiliate_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.approve"))):
    return {"status": "success", "message": "Affiliate approved successfully", "data": approve_affiliate(db, affiliate_id, current_user, request)}


@router.patch("/{affiliate_id}/reject")
def reject(affiliate_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.reject"))):
    return {"status": "success", "message": "Affiliate rejected successfully", "data": reject_affiliate(db, affiliate_id, data, current_user, request)}


@router.patch("/{affiliate_id}/api-link")
def api_link(affiliate_id: int, data: AffiliateApiLinkRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.manage_api_link"))):
    return {"status": "success", "message": "Affiliate API link updated successfully", "data": update_affiliate_api_link(db, affiliate_id, data, current_user, request)}
