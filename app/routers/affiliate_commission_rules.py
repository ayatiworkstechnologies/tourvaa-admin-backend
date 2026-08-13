from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.permissions import require_any_permission
from app.database import get_db
from app.schemas.affiliate_tracking import AffiliateCommissionRuleCreate, AffiliateCommissionRuleUpdate
from app.services import affiliate_commission_rules as service
from app.utils.pagination import pagination_params

router = APIRouter(prefix="/affiliate-commission-rules", tags=["Affiliate Commission Rules"])


@router.get("")
@router.get("/")
def list_rules(
    pagination=Depends(pagination_params),
    affiliate_id: int = Query(default=0),
    tour_id: int = Query(default=0),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("affiliate_commission_rules.view")),
):
    return {
        "status": "success",
        **service.list_rules(db, affiliate_id=affiliate_id or None, tour_id=tour_id or None, is_active=is_active, page=pagination["page"], limit=pagination["limit"]),
    }


@router.post("")
@router.post("/")
def create_rule(data: AffiliateCommissionRuleCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_commission_rules.create"))):
    return {"status": "success", "message": "Commission rule created", "data": service.create_rule(db, data, current_user)}


@router.get("/{rule_id}")
def rule_detail(rule_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliate_commission_rules.view"))):
    return {"status": "success", "data": service._s_rule(service.get_rule(db, rule_id))}


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: AffiliateCommissionRuleUpdate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_commission_rules.update"))):
    return {"status": "success", "message": "Commission rule updated", "data": service.update_rule(db, rule_id, data, current_user)}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_commission_rules.delete"))):
    return {"status": "success", "data": service.delete_rule(db, rule_id, current_user)}
