from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import affiliate_tracking as service
from app.services import messaging as messaging_service
from app.schemas.affiliate_tracking import AffiliateLinkCreate, AffiliateLinkUpdate, AffiliatePayoutCreate
from app.schemas.bookings import BookingCommunicationCreate
from app.auth.permissions import require_any_permission, get_current_user
from app.models.users import User
from app.utils.pagination import pagination_params

router = APIRouter(tags=["Affiliate Tracking"])


@router.post("/affiliates/{affiliate_id}/links")
def create_link(affiliate_id: int, data: AffiliateLinkCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    is_admin = not service.is_affiliate_user(current_user)
    result = service.create_link(db, affiliate_id=affiliate_id, data=data, actor=current_user, is_admin=is_admin)
    return {"status": "success", "data": result}


@router.get("/affiliates/{affiliate_id}/links")
def list_links(affiliate_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    return {"status": "success", "data": service.list_links(db, affiliate_id=affiliate_id)}


@router.get("/affiliates/{affiliate_id}/links/{link_id}")
def link_detail(affiliate_id: int, link_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    link = service.get_link(db, link_id)
    if link.affiliate_id != affiliate_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Affiliate link not found")
    return {"status": "success", "data": service._s_link(link)}


@router.put("/affiliates/{affiliate_id}/links/{link_id}")
def update_own_link(affiliate_id: int, link_id: int, data: AffiliateLinkUpdate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_links.update"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    link = service.get_link(db, link_id)
    if link.affiliate_id != affiliate_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Affiliate link not found")
    result = service.update_link(db, link_id, data, current_user, is_admin=False)
    return {"status": "success", "message": "Link updated", "data": result}


# Public click-tracking endpoint (no auth needed)
@router.get("/affiliates/track/{ref_code}")
def track_click(ref_code: str, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    referrer = request.headers.get("referer")
    result = service.track_click(db, ref_code=ref_code, ip_address=ip, user_agent=ua, referrer=referrer)
    return {"status": "success", "data": result}


@router.get("/affiliates/{affiliate_id}/clicks")
def list_clicks(affiliate_id: int, pagination=Depends(pagination_params), db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    return {"status": "success", **service.list_clicks(db, affiliate_id=affiliate_id, page=pagination["page"], limit=pagination["limit"])}


@router.get("/affiliates/{affiliate_id}/conversions")
def list_conversions(affiliate_id: int, pagination=Depends(pagination_params), db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    return {"status": "success", **service.list_conversions(db, affiliate_id=affiliate_id, page=pagination["page"], limit=pagination["limit"])}


@router.get("/affiliates/{affiliate_id}/commissions")
def get_commissions(affiliate_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    service.ensure_affiliate_access(db, affiliate_id, current_user)
    return {"status": "success", "data": service.get_commissions(db, affiliate_id=affiliate_id)}


@router.get("/affiliate-payouts")
def list_payouts(pagination=Depends(pagination_params), affiliate_id: int = Query(default=0), db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.view", "view-affiliates"))):
    if service.is_affiliate_user(current_user):
        # Affiliates only ever see their own payouts - ignore/override
        # whatever affiliate_id was requested, same pattern as the agent
        # portal forcing agent_id on its own customer list.
        affiliate_id = service.get_actor_affiliate(db, current_user).id
    return {"status": "success", **service.list_payouts(db, affiliate_id=affiliate_id or None, page=pagination["page"], limit=pagination["limit"])}


@router.post("/affiliate-payouts")
def create_payout(data: AffiliatePayoutCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliates.approve"))):
    # Payout creation is admin-only (it immediately marks conversions paid),
    # so this intentionally does NOT accept "view-affiliates" - a plain
    # affiliate role only holds affiliates.view/view-affiliates and must not
    # be able to create a payout for any affiliate_id, including their own.
    result = service.create_payout(db, data=data, actor=current_user)
    return {"status": "success", "message": "Affiliate payout created", "data": result}


# Affiliate <-> admin support messaging - mirrors the existing
# supplier/agent/customer "own conversation" endpoints in bookings.py /
# customers_portal.py, extended to the "affiliate" participant type.
@router.get("/affiliate/messages")
async def affiliate_messages(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": messaging_service.get_own_conversation_thread(db, current_user)}


@router.post("/affiliate/messages")
async def send_affiliate_message(data: BookingCommunicationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = await messaging_service.send_message_as_participant(db, current_user, data.message)
    return {"status": "success", "message": "Message sent successfully", "data": message}
