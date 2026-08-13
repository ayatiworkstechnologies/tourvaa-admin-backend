"""Affiliate wallet/payout-method self-service, the affiliate-initiated
payout request, and the admin approve/reject/process/mark-paid actions on it.

The older admin-direct "pick conversions, pay now" endpoints
(GET/POST /affiliate-payouts) stay in affiliate_tracking.py unchanged.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.permissions import require_any_permission
from app.database import get_db
from app.schemas.affiliate_tracking import (
    AffiliatePayoutMarkPaid,
    AffiliatePayoutMethodCreate,
    AffiliatePayoutMethodUpdate,
    AffiliatePayoutReject,
    AffiliatePayoutRequestCreate,
)
from app.services import affiliate_payouts as service
from app.services.affiliate_tracking import get_actor_affiliate
from app.utils.pagination import pagination_params

router = APIRouter(tags=["Affiliate Payouts"])


# --- self-service: payout methods -------------------------------------------

@router.get("/affiliate/payout-methods")
def list_payout_methods(db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.view"))):
    aff = get_actor_affiliate(db, current_user)
    return {"status": "success", "data": service.list_payout_methods(db, aff.id)}


@router.post("/affiliate/payout-methods")
def create_payout_method(data: AffiliatePayoutMethodCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.create"))):
    aff = get_actor_affiliate(db, current_user)
    return {"status": "success", "message": "Payout method added", "data": service.create_payout_method(db, aff.id, data)}


@router.put("/affiliate/payout-methods/{method_id}")
def update_payout_method(method_id: int, data: AffiliatePayoutMethodUpdate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.create"))):
    aff = get_actor_affiliate(db, current_user)
    return {"status": "success", "message": "Payout method updated", "data": service.update_payout_method(db, aff.id, method_id, data)}


@router.delete("/affiliate/payout-methods/{method_id}")
def delete_payout_method(method_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.create"))):
    aff = get_actor_affiliate(db, current_user)
    service.delete_payout_method(db, aff.id, method_id)
    return {"status": "success", "message": "Payout method removed"}


# --- self-service: wallet ----------------------------------------------------

@router.get("/affiliate/wallet")
def wallet_summary(db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.view", "affiliates.view", "view-affiliates"))):
    aff = get_actor_affiliate(db, current_user)
    return {"status": "success", "data": service.get_wallet_summary(db, aff.id)}


@router.get("/affiliate/wallet/transactions")
def wallet_transactions(pagination=Depends(pagination_params), db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.view", "affiliates.view", "view-affiliates"))):
    aff = get_actor_affiliate(db, current_user)
    return {"status": "success", **service.list_wallet_transactions(db, aff.id, page=pagination["page"], limit=pagination["limit"])}


# --- self-service: payout request --------------------------------------------

@router.post("/affiliate/payout-requests")
def request_payout(data: AffiliatePayoutRequestCreate, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.create"))):
    aff = get_actor_affiliate(db, current_user)
    return {"status": "success", "message": "Payout requested", "data": service.request_payout(db, aff, data)}


# --- admin: payout queue -------------------------------------------------------

@router.get("/admin/affiliate-payouts")
def admin_list_payouts(pagination=Depends(pagination_params), status: str = "", db: Session = Depends(get_db), _=Depends(require_any_permission("affiliate_payouts.approve", "affiliate_payouts.view"))):
    return {"status": "success", **service.list_affiliate_payouts_admin(db, status=status, page=pagination["page"], limit=pagination["limit"])}


@router.post("/affiliate-payouts/{payout_id}/approve")
def approve_payout(payout_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.approve"))):
    return {"status": "success", "message": "Payout approved", "data": service.approve_payout(db, payout_id, current_user)}


@router.post("/affiliate-payouts/{payout_id}/reject")
def reject_payout(payout_id: int, data: AffiliatePayoutReject, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.reject"))):
    return {"status": "success", "message": "Payout rejected", "data": service.reject_payout(db, payout_id, data.reason, current_user)}


@router.post("/affiliate-payouts/{payout_id}/processing")
def mark_processing(payout_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.process"))):
    return {"status": "success", "message": "Payout marked processing", "data": service.mark_payout_processing(db, payout_id, current_user)}


@router.post("/affiliate-payouts/{payout_id}/mark-paid")
def mark_paid(payout_id: int, data: AffiliatePayoutMarkPaid, db: Session = Depends(get_db), current_user=Depends(require_any_permission("affiliate_payouts.process", "affiliate_payouts.mark_paid"))):
    return {"status": "success", "message": "Payout marked paid", "data": service.mark_payout_paid(db, payout_id, payment_reference=data.payment_reference, admin_notes=data.admin_notes, actor=current_user)}
