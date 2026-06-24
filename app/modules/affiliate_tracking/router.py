from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.affiliate_tracking import service
from app.modules.affiliate_tracking.schemas import AffiliateLinkCreate, AffiliatePayoutCreate
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params

router = APIRouter(tags=["Affiliate Tracking"])


@router.post("/affiliates/{affiliate_id}/links")
def create_link(affiliate_id: int, data: AffiliateLinkCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    result = service.create_link(db, affiliate_id=affiliate_id, data=data, actor=current_user)
    return {"status": "success", "data": result}


@router.get("/affiliates/{affiliate_id}/links")
def list_links(affiliate_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    return {"status": "success", "data": service.list_links(db, affiliate_id=affiliate_id)}


# Public click-tracking endpoint (no auth needed)
@router.get("/affiliates/track/{ref_code}")
def track_click(ref_code: str, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    referrer = request.headers.get("referer")
    result = service.track_click(db, ref_code=ref_code, ip_address=ip, user_agent=ua, referrer=referrer)
    return {"status": "success", "data": result}


@router.get("/affiliates/{affiliate_id}/clicks")
def list_clicks(affiliate_id: int, pagination=Depends(pagination_params), db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    return {"status": "success", **service.list_clicks(db, affiliate_id=affiliate_id, page=pagination["page"], limit=pagination["limit"])}


@router.get("/affiliates/{affiliate_id}/conversions")
def list_conversions(affiliate_id: int, pagination=Depends(pagination_params), db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    return {"status": "success", **service.list_conversions(db, affiliate_id=affiliate_id, page=pagination["page"], limit=pagination["limit"])}


@router.get("/affiliates/{affiliate_id}/commissions")
def get_commissions(affiliate_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    return {"status": "success", "data": service.get_commissions(db, affiliate_id=affiliate_id)}


@router.get("/affiliate-payouts")
def list_payouts(pagination=Depends(pagination_params), affiliate_id: int = Query(default=0), db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    return {"status": "success", **service.list_payouts(db, affiliate_id=affiliate_id or None, page=pagination["page"], limit=pagination["limit"])}


@router.post("/affiliate-payouts")
def create_payout(data: AffiliatePayoutCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.approve", "view-affiliates"))):
    result = service.create_payout(db, data=data, actor=current_user)
    return {"status": "success", "message": "Affiliate payout created", "data": result}
