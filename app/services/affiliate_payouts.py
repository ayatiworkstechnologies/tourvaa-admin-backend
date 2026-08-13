"""Affiliate payout methods + the affiliate-initiated payout request lifecycle
(REQUESTED -> APPROVED -> PROCESSING -> PAID, or REJECTED).

Distinct from affiliate_tracking.create_payout, which is the older
admin-direct "pick conversions, pay immediately" action - that endpoint stays
working unchanged for whatever already calls it. This module is the new path
where the affiliate asks for money first and admin reviews the request.

Ledger accounting: a request HOLDs the requested conversions' commission
(PAYOUT_HOLD, negative) at request time - that single ledger movement is what
takes the money out of "available balance". Rejecting the request reverses it
(PAYOUT_RELEASE, positive). Reaching PAID does not add another ledger
movement - the money already left "available" at HOLD time and paid is just a
status/finality change, so summing all wallet_transactions.amount always
equals the affiliate's current available balance without double-counting.
"""
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.affiliate_tracking import AffiliateConversion, AffiliatePayout, AffiliatePayoutItem, AffiliatePayoutMethod, AffiliateWalletTransaction
from app.models.affiliates import Affiliate
from app.models.users import User
from app.schemas.affiliate_tracking import AffiliatePayoutMethodCreate, AffiliatePayoutMethodUpdate, AffiliatePayoutRequestCreate
from app.services.affiliate_tracking import _payout_code, _s_payout, _wallet_entry
from app.services.audit import log_audit
from app.services.notifications import enqueue_notification, notify_admins
from app.utils.money import money, utcnow


def get_minimum_payout(db: Session) -> Decimal:
    from app.services.settings import get_affiliate_setting
    try:
        return money(get_affiliate_setting(db, "affiliate_minimum_payout", "50"))
    except Exception:
        return money("50")


def _s_method(r: AffiliatePayoutMethod) -> dict:
    masked_account = f"XXXX{r.account_number[-4:]}" if r.account_number and len(r.account_number) >= 4 else (r.account_number or "")
    return {
        "id": r.id, "affiliate_id": r.affiliate_id, "method_type": r.method_type,
        "account_holder_name": r.account_holder_name, "bank_name": r.bank_name,
        "account_number_masked": masked_account, "ifsc": r.ifsc, "swift_code": r.swift_code,
        "bank_country": r.bank_country, "paypal_email": r.paypal_email,
        "is_default": r.is_default, "is_active": r.is_active, "created_at": r.created_at,
    }


# payout methods

def create_payout_method(db: Session, affiliate_id: int, data: AffiliatePayoutMethodCreate) -> dict:
    if data.is_default:
        db.query(AffiliatePayoutMethod).filter(AffiliatePayoutMethod.affiliate_id == affiliate_id).update({"is_default": False})
    method = AffiliatePayoutMethod(affiliate_id=affiliate_id, **data.model_dump())
    db.add(method)
    db.commit()
    db.refresh(method)
    return _s_method(method)


def list_payout_methods(db: Session, affiliate_id: int) -> list:
    return [_s_method(r) for r in db.query(AffiliatePayoutMethod).filter(AffiliatePayoutMethod.affiliate_id == affiliate_id).order_by(AffiliatePayoutMethod.id.desc()).all()]


def update_payout_method(db: Session, affiliate_id: int, method_id: int, data: AffiliatePayoutMethodUpdate) -> dict:
    method = db.query(AffiliatePayoutMethod).filter(AffiliatePayoutMethod.id == method_id, AffiliatePayoutMethod.affiliate_id == affiliate_id).first()
    if not method:
        raise HTTPException(status_code=404, detail="Payout method not found")
    updates = data.model_dump(exclude_unset=True)
    if updates.get("is_default"):
        db.query(AffiliatePayoutMethod).filter(AffiliatePayoutMethod.affiliate_id == affiliate_id, AffiliatePayoutMethod.id != method_id).update({"is_default": False})
    for key, value in updates.items():
        setattr(method, key, value)
    db.commit()
    db.refresh(method)
    return _s_method(method)


def delete_payout_method(db: Session, affiliate_id: int, method_id: int) -> None:
    method = db.query(AffiliatePayoutMethod).filter(AffiliatePayoutMethod.id == method_id, AffiliatePayoutMethod.affiliate_id == affiliate_id).first()
    if not method:
        raise HTTPException(status_code=404, detail="Payout method not found")
    if db.query(AffiliatePayout).filter(AffiliatePayout.payout_method_id == method_id).first():
        # Has payout history against it - deactivate instead of deleting so
        # past payouts keep a resolvable method reference.
        method.is_active = False
        db.commit()
        return
    db.delete(method)
    db.commit()


# payout request lifecycle

def get_available_balance(db: Session, affiliate_id: int) -> Decimal:
    payable_statuses = ("pending", "confirmed")
    held_conversion_ids = {row[0] for row in db.query(AffiliatePayoutItem.conversion_id).join(AffiliatePayout).filter(AffiliatePayout.affiliate_id == affiliate_id).all()}
    rows = db.query(AffiliateConversion).filter(AffiliateConversion.affiliate_id == affiliate_id, AffiliateConversion.status.in_(payable_statuses)).all()
    return money(sum((r.final_commission if r.final_commission is not None else r.commission_amount) for r in rows if r.id not in held_conversion_ids))


def get_wallet_summary(db: Session, affiliate_id: int) -> dict:
    payable_statuses = ("pending", "confirmed")
    # Only conversions attached to a payout that's still in flight (not yet
    # paid, not rejected/cancelled - rejected payouts already have their
    # items deleted in reject_payout) count as "held", so a paid payout's
    # conversions correctly fall out of the held bucket into paid_lifetime.
    held_conversion_ids = {
        row[0] for row in db.query(AffiliatePayoutItem.conversion_id)
        .join(AffiliatePayout)
        .filter(AffiliatePayout.affiliate_id == affiliate_id, AffiliatePayout.status.in_(("requested", "approved", "processing")))
        .all()
    }
    conversions = db.query(AffiliateConversion).filter(AffiliateConversion.affiliate_id == affiliate_id).all()

    def amt(c):
        return c.final_commission if c.final_commission is not None else c.commission_amount

    pending = money(sum(amt(c) for c in conversions if c.status in payable_statuses and c.id not in held_conversion_ids))
    held = money(sum(amt(c) for c in conversions if c.id in held_conversion_ids))
    paid = money(sum(amt(c) for c in conversions if c.status == "paid"))
    lifetime = money(sum(amt(c) for c in conversions if c.status not in ("void", "reversed")))

    ledger_rows = db.query(AffiliateWalletTransaction.amount).filter(AffiliateWalletTransaction.affiliate_id == affiliate_id).all()
    ledger_balance = money(sum(row[0] for row in ledger_rows))

    return {
        "affiliate_id": affiliate_id,
        "available_balance": str(pending),
        "pending_payout_balance": str(held),
        "paid_lifetime": str(paid),
        "lifetime_earnings": str(lifetime),
        "ledger_balance": str(ledger_balance),
    }


def list_wallet_transactions(db: Session, affiliate_id: int, page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliateWalletTransaction).filter(AffiliateWalletTransaction.affiliate_id == affiliate_id).order_by(AffiliateWalletTransaction.id.desc())
    total = q.count()
    items = [
        {
            "id": r.id, "transaction_type": r.transaction_type, "amount": str(r.amount), "currency": r.currency,
            "commission_id": r.commission_id, "payout_id": r.payout_id, "reference_type": r.reference_type,
            "reference_id": r.reference_id, "description": r.description, "created_at": r.created_at,
        }
        for r in q.offset((page - 1) * limit).limit(limit).all()
    ]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def request_payout(db: Session, affiliate: Affiliate, data: AffiliatePayoutRequestCreate, request=None) -> dict:
    if (affiliate.status or "").lower() != "active":
        raise HTTPException(status_code=403, detail="Affiliate account is not active")

    method = db.query(AffiliatePayoutMethod).filter(AffiliatePayoutMethod.id == data.payout_method_id, AffiliatePayoutMethod.affiliate_id == affiliate.id, AffiliatePayoutMethod.is_active == True).first()  # noqa: E712
    if not method:
        raise HTTPException(status_code=404, detail="Payout method not found")

    amount = money(data.amount)
    minimum = get_minimum_payout(db)
    if amount < minimum:
        raise HTTPException(status_code=400, detail=f"Minimum payout amount is {minimum}")

    # Lock candidate conversions before deciding what's available so two
    # concurrent requests from the same affiliate can't both draw on the
    # same commission (mirrors affiliate_tracking.create_payout's row-lock
    # pattern for the same reason).
    held_conversion_ids = {row[0] for row in db.query(AffiliatePayoutItem.conversion_id).join(AffiliatePayout).filter(AffiliatePayout.affiliate_id == affiliate.id).all()}
    candidates = (
        db.query(AffiliateConversion)
        .filter(AffiliateConversion.affiliate_id == affiliate.id, AffiliateConversion.status.in_(("pending", "confirmed")))
        .order_by(AffiliateConversion.id.asc())
        .with_for_update()
        .all()
    )
    candidates = [c for c in candidates if c.id not in held_conversion_ids]

    available = money(sum((c.final_commission if c.final_commission is not None else c.commission_amount) for c in candidates))
    if amount > available:
        raise HTTPException(status_code=400, detail=f"Requested amount exceeds available balance ({available})")

    selected = []
    running_total = money(0)
    for c in candidates:
        if running_total >= amount:
            break
        selected.append(c)
        running_total += money(c.final_commission if c.final_commission is not None else c.commission_amount)

    payout = AffiliatePayout(
        affiliate_id=affiliate.id,
        payout_method_id=method.id,
        total_amount=running_total,
        currency=selected[0].currency if selected else "USD",
        payment_method=method.method_type,
        status="requested",
        notes=data.notes,
        initiated_by=affiliate.user_id,
        requested_at=utcnow(),
    )
    db.add(payout)
    db.flush()
    payout.payout_code = _payout_code(payout.id)

    for c in selected:
        db.add(AffiliatePayoutItem(payout_id=payout.id, conversion_id=c.id, amount=c.final_commission if c.final_commission is not None else c.commission_amount))

    _wallet_entry(
        db, affiliate_id=affiliate.id, transaction_type="PAYOUT_HOLD", amount=-running_total,
        currency=payout.currency, payout_id=payout.id, reference_type="affiliate_payout", reference_id=payout.id,
        description=f"Held for payout request {payout.payout_code}",
    )

    log_audit(db, actor=None, action="request_affiliate_payout", entity_type="affiliate_payout", entity_id=payout.id, new_values=_s_payout(payout), request=request)
    notify_admins(db, notification_type="affiliate_payout_requested", title="Affiliate Payout Requested", message=f"{affiliate.name} requested a payout of {running_total} {payout.currency}.", entity_type="affiliate_payout", entity_id=payout.id)

    db.commit()
    db.refresh(payout)
    return _s_payout(payout)


def list_affiliate_payouts_admin(db: Session, *, affiliate_id: Optional[int] = None, status: str = "", page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliatePayout)
    if affiliate_id:
        q = q.filter(AffiliatePayout.affiliate_id == affiliate_id)
    if status:
        q = q.filter(AffiliatePayout.status == status)
    q = q.order_by(AffiliatePayout.id.desc())
    total = q.count()
    items = [_s_payout(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def _get_payout_for_update(db: Session, payout_id: int) -> AffiliatePayout:
    payout = db.query(AffiliatePayout).filter(AffiliatePayout.id == payout_id).with_for_update().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    return payout


def approve_payout(db: Session, payout_id: int, actor: User, request=None) -> dict:
    payout = _get_payout_for_update(db, payout_id)
    if payout.status != "requested":
        raise HTTPException(status_code=400, detail=f"Payout is already '{payout.status}'")
    old = _s_payout(payout)
    payout.status = "approved"
    payout.approved_by = actor.id
    payout.approved_at = utcnow()
    log_audit(db, actor=actor, action="approve_affiliate_payout", entity_type="affiliate_payout", entity_id=payout.id, old_values=old, new_values=_s_payout(payout), request=request)
    db.commit()
    db.refresh(payout)
    _notify_affiliate(db, payout, "affiliate_payout_approved", "Payout Approved", f"Your payout request {payout.payout_code} for {payout.total_amount} {payout.currency} was approved.")
    return _s_payout(payout)


def reject_payout(db: Session, payout_id: int, reason: str, actor: User, request=None) -> dict:
    payout = _get_payout_for_update(db, payout_id)
    if payout.status not in ("requested", "approved"):
        raise HTTPException(status_code=400, detail=f"Payout is already '{payout.status}'")
    old = _s_payout(payout)
    payout.status = "rejected"
    payout.rejected_by = actor.id
    payout.rejected_at = utcnow()
    payout.rejection_reason = reason

    # Release the hold: unlink the conversions so they become requestable
    # again, and reverse the earlier PAYOUT_HOLD ledger entry.
    db.query(AffiliatePayoutItem).filter(AffiliatePayoutItem.payout_id == payout.id).delete()
    _wallet_entry(
        db, affiliate_id=payout.affiliate_id, transaction_type="PAYOUT_RELEASE", amount=payout.total_amount,
        currency=payout.currency, payout_id=payout.id, reference_type="affiliate_payout", reference_id=payout.id,
        description=f"Released - payout request {payout.payout_code} rejected",
    )

    log_audit(db, actor=actor, action="reject_affiliate_payout", entity_type="affiliate_payout", entity_id=payout.id, old_values=old, new_values=_s_payout(payout), request=request)
    db.commit()
    db.refresh(payout)
    _notify_affiliate(db, payout, "affiliate_payout_rejected", "Payout Rejected", f"Your payout request {payout.payout_code} was rejected: {reason}")
    return _s_payout(payout)


def mark_payout_processing(db: Session, payout_id: int, actor: User, request=None) -> dict:
    payout = _get_payout_for_update(db, payout_id)
    if payout.status != "approved":
        raise HTTPException(status_code=400, detail=f"Payout must be 'approved' before processing (currently '{payout.status}')")
    old = _s_payout(payout)
    payout.status = "processing"
    payout.processing_at = utcnow()
    log_audit(db, actor=actor, action="process_affiliate_payout", entity_type="affiliate_payout", entity_id=payout.id, old_values=old, new_values=_s_payout(payout), request=request)
    db.commit()
    db.refresh(payout)
    _notify_affiliate(db, payout, "affiliate_payout_processing", "Payout Processing", f"Your payout request {payout.payout_code} is now being processed.")
    return _s_payout(payout)


def mark_payout_paid(db: Session, payout_id: int, *, payment_reference: str, admin_notes: Optional[str], actor: User, request=None) -> dict:
    payout = _get_payout_for_update(db, payout_id)
    if payout.status not in ("processing", "approved"):
        raise HTTPException(status_code=400, detail=f"Payout must be 'approved' or 'processing' before marking paid (currently '{payout.status}')")
    old = _s_payout(payout)
    payout.status = "paid"
    payout.reference_number = payment_reference
    if admin_notes:
        payout.notes = admin_notes
    payout.paid_at = utcnow()

    items = db.query(AffiliatePayoutItem).filter(AffiliatePayoutItem.payout_id == payout.id).all()
    conversion_ids = [i.conversion_id for i in items]
    if conversion_ids:
        db.query(AffiliateConversion).filter(AffiliateConversion.id.in_(conversion_ids)).update({"status": "paid"}, synchronize_session=False)

    log_audit(db, actor=actor, action="mark_paid_affiliate_payout", entity_type="affiliate_payout", entity_id=payout.id, old_values=old, new_values=_s_payout(payout), request=request)
    db.commit()
    db.refresh(payout)
    _notify_affiliate(db, payout, "affiliate_payout_paid", "Payout Paid", f"Your payout {payout.payout_code} of {payout.total_amount} {payout.currency} has been paid.")
    return _s_payout(payout)


def _notify_affiliate(db: Session, payout: AffiliatePayout, notification_type: str, title: str, message: str) -> None:
    aff = db.query(Affiliate).filter(Affiliate.id == payout.affiliate_id).first()
    if aff and aff.user_id:
        enqueue_notification(db, user_id=aff.user_id, notification_type=notification_type, title=title, message=message, entity_type="affiliate_payout", entity_id=payout.id)
        db.commit()
