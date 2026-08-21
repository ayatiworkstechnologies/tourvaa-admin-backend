from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.affiliates import AffiliateApiLinkRequest, AffiliateCreate, AffiliateSuspendRequest, AffiliateUpdate
from app.services.affiliates import activate_affiliate, approve_affiliate, create_affiliate, get_affiliate, list_affiliates, reject_affiliate, serialize_affiliate, suspend_affiliate, update_affiliate, update_affiliate_api_link
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


@router.post("")
@router.post("/")
def add_affiliate(data: AffiliateCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.create", "affiliates.approve"))):
    return {"status": "success", "message": "Affiliate created successfully", "data": create_affiliate(db, data, current_user, request)}


@router.get("/{affiliate_id}")
def affiliate_detail(affiliate_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view"))):
    return {"status": "success", "data": serialize_affiliate(get_affiliate(db, affiliate_id))}


@router.put("/{affiliate_id}")
def edit_affiliate(affiliate_id: int, data: AffiliateUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.approve"))):
    return {"status": "success", "message": "Affiliate updated successfully", "data": update_affiliate(db, affiliate_id, data, current_user, request)}


@router.get("/{affiliate_id}/commission-calculator")
def affiliate_commission_calculator(
    affiliate_id: int,
    amount: float = Query(ge=0),
    tour_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("affiliates.view")),
):
    """Read-only preview of what Tourvaa would pay this affiliate on a
    booking of the given amount, using the same rule-resolution hierarchy
    (link -> affiliate+tour -> affiliate -> tour -> category -> global
    default) as a real conversion - see
    services.affiliate_commission.resolve_affiliate_commission_rule. Does
    not account for a link-level override, since this preview has no
    specific link."""
    from app.utils.money import money
    from app.models.cms import Tour
    from app.services.affiliate_commission import resolve_affiliate_commission_rule

    affiliate = get_affiliate(db, affiliate_id)
    eligible_amount = money(amount)
    tour = db.query(Tour).filter(Tour.id == tour_id).first() if tour_id else None
    rule = resolve_affiliate_commission_rule(
        db,
        affiliate_id=affiliate.id,
        tour_id=tour_id,
        category_id=tour.category_id if tour else None,
    )
    if rule:
        commission_type = rule.commission_type
        percentage = money(rule.percentage or 0)
        fixed_amount = money(rule.fixed_amount or 0)
    else:
        commission_type = "percentage"
        percentage = money(affiliate.commission_percentage or 0)
        fixed_amount = money(0)
    commission_amount = fixed_amount if commission_type == "fixed" else money(eligible_amount * percentage / money(100))
    return {
        "status": "success",
        "data": {
            "gross_amount": str(eligible_amount),
            "commission_type": commission_type,
            "commission_percentage": str(percentage) if commission_type == "percentage" else None,
            "commission_amount": str(commission_amount),
            "matched_rule_id": rule.id if rule else None,
        },
    }


@router.patch("/{affiliate_id}/approve")
def approve(affiliate_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.approve"))):
    return {"status": "success", "message": "Affiliate approved successfully", "data": approve_affiliate(db, affiliate_id, current_user, request)}


@router.patch("/{affiliate_id}/reject")
def reject(affiliate_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.reject"))):
    return {"status": "success", "message": "Affiliate rejected successfully", "data": reject_affiliate(db, affiliate_id, data, current_user, request)}


@router.post("/{affiliate_id}/activate")
def activate(affiliate_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.activate"))):
    return {"status": "success", "message": "Affiliate activated successfully", "data": activate_affiliate(db, affiliate_id, current_user, request)}


@router.post("/{affiliate_id}/suspend")
def suspend(affiliate_id: int, data: AffiliateSuspendRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.suspend"))):
    return {"status": "success", "message": "Affiliate suspended successfully", "data": suspend_affiliate(db, affiliate_id, data, current_user, request)}


@router.patch("/{affiliate_id}/api-link")
def api_link(affiliate_id: int, data: AffiliateApiLinkRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.manage_api_link"))):
    return {"status": "success", "message": "Affiliate API link updated successfully", "data": update_affiliate_api_link(db, affiliate_id, data, current_user, request)}
