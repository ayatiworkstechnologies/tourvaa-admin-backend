import secrets
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models.affiliate_tracking import AffiliateClick, AffiliateConversion, AffiliateLink, AffiliatePayout
from app.schemas.affiliate_tracking import AffiliateLinkCreate, AffiliatePayoutCreate
from app.models.affiliates import Affiliate
from app.utils.money import money, utcnow
from app.services.notifications import enqueue_notification
from app.models.users import User


def _ref_code() -> str:
    return secrets.token_urlsafe(12).upper()


def _payout_code(payout_id: int) -> str:
    return f"AFF-PAY-{payout_id:06d}"


def _s_link(r: AffiliateLink) -> dict:
    return {"id": r.id, "affiliate_id": r.affiliate_id, "ref_code": r.ref_code, "destination_url": r.destination_url, "label": r.label, "is_active": r.is_active, "total_clicks": len(r.clicks), "total_conversions": len(r.conversions), "created_at": r.created_at}


def _s_click(r: AffiliateClick) -> dict:
    return {"id": r.id, "link_id": r.link_id, "affiliate_id": r.affiliate_id, "ip_address": r.ip_address, "referrer": r.referrer, "clicked_at": r.clicked_at}


def _s_conversion(r: AffiliateConversion) -> dict:
    return {"id": r.id, "link_id": r.link_id, "affiliate_id": r.affiliate_id, "booking_id": r.booking_id, "booking_code": r.booking.booking_code if r.booking else None, "booking_amount": str(r.booking_amount), "commission_percentage": str(r.commission_percentage), "commission_amount": str(r.commission_amount), "currency": r.currency, "status": r.status, "converted_at": r.converted_at}


def _s_payout(r: AffiliatePayout) -> dict:
    return {"id": r.id, "payout_code": r.payout_code, "affiliate_id": r.affiliate_id, "total_amount": str(r.total_amount), "currency": r.currency, "payment_method": r.payment_method, "reference_number": r.reference_number, "status": r.status, "notes": r.notes, "paid_at": r.paid_at, "created_at": r.created_at}


# links

def create_link(db: Session, affiliate_id: int, data: AffiliateLinkCreate, actor: User) -> dict:
    aff = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not aff:
        raise HTTPException(status_code=404, detail="Affiliate not found")
    link = AffiliateLink(affiliate_id=affiliate_id, ref_code=_ref_code(), label=data.label, destination_url=data.destination_url)
    db.add(link)
    db.commit()
    db.refresh(link)
    return _s_link(link)


def list_links(db: Session, affiliate_id: int) -> list:
    return [_s_link(r) for r in db.query(AffiliateLink).filter(AffiliateLink.affiliate_id == affiliate_id).order_by(AffiliateLink.id.desc()).all()]


def track_click(db: Session, ref_code: str, ip_address: Optional[str] = None, user_agent: Optional[str] = None, referrer: Optional[str] = None) -> dict:
    link = db.query(AffiliateLink).filter(AffiliateLink.ref_code == ref_code, AffiliateLink.is_active == True).first()
    if not link:
        raise HTTPException(status_code=404, detail="Referral link not found")
    click = AffiliateClick(link_id=link.id, affiliate_id=link.affiliate_id, ip_address=ip_address, user_agent=user_agent, referrer=referrer)
    db.add(click)
    db.commit()
    return {"ref_code": ref_code, "redirect_url": link.destination_url or "/", "tracked": True}


# clicks & conversions

def list_clicks(db: Session, affiliate_id: int, page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliateClick).filter(AffiliateClick.affiliate_id == affiliate_id).order_by(AffiliateClick.id.desc())
    total = q.count()
    items = [_s_click(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def list_conversions(db: Session, affiliate_id: int, page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliateConversion).filter(AffiliateConversion.affiliate_id == affiliate_id).order_by(AffiliateConversion.id.desc())
    total = q.count()
    items = [_s_conversion(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def record_conversion(db: Session, *, ref_code: str, booking_id: int, booking_amount: Decimal, currency: str = "USD") -> Optional[AffiliateConversion]:
    """Called from booking service when a booking is confirmed and has a ref_code."""
    link = db.query(AffiliateLink).filter(AffiliateLink.ref_code == ref_code, AffiliateLink.is_active == True).first()
    if not link:
        return None
    aff = db.query(Affiliate).filter(Affiliate.id == link.affiliate_id).first()
    if not aff:
        return None

    # Check for existing conversion for this booking
    existing = db.query(AffiliateConversion).filter(AffiliateConversion.booking_id == booking_id).first()
    if existing:
        return existing

    # Try common commission field names; default to 0 if not present
    commission_pct = Decimal(str(getattr(aff, "commission_value", None) or getattr(aff, "commission_percentage", None) or 0))
    commission_amount = money((money(booking_amount) * commission_pct) / 100)

    conversion = AffiliateConversion(
        link_id=link.id,
        affiliate_id=link.affiliate_id,
        booking_id=booking_id,
        booking_amount=money(booking_amount),
        commission_percentage=commission_pct,
        commission_amount=commission_amount,
        currency=currency,
        status="pending",
    )
    db.add(conversion)
    db.flush()
    return conversion


# commission summary

def get_commissions(db: Session, affiliate_id: int) -> dict:
    rows = db.query(AffiliateConversion).filter(AffiliateConversion.affiliate_id == affiliate_id).all()
    total_commission = sum(money(r.commission_amount) for r in rows)
    pending = sum(money(r.commission_amount) for r in rows if r.status == "pending")
    confirmed = sum(money(r.commission_amount) for r in rows if r.status == "confirmed")
    paid = sum(money(r.commission_amount) for r in rows if r.status == "paid")
    return {
        "affiliate_id": affiliate_id,
        "total_conversions": len(rows),
        "total_commission": str(total_commission),
        "pending_commission": str(pending),
        "confirmed_commission": str(confirmed),
        "paid_commission": str(paid),
        "entries": [_s_conversion(r) for r in rows],
    }


# payouts

def create_payout(db: Session, data: AffiliatePayoutCreate, actor: User) -> dict:
    conversions = db.query(AffiliateConversion).filter(
        AffiliateConversion.id.in_(data.conversion_ids),
        AffiliateConversion.affiliate_id == data.affiliate_id,
        AffiliateConversion.status.in_(["pending", "confirmed"]),
    ).all()
    if not conversions:
        raise HTTPException(status_code=404, detail="No payable conversions found")

    total = money(sum(r.commission_amount for r in conversions))
    payout = AffiliatePayout(
        affiliate_id=data.affiliate_id,
        total_amount=total,
        currency=conversions[0].currency,
        payment_method=data.payment_method,
        reference_number=data.reference_number,
        status="pending",
        notes=data.notes,
        initiated_by=actor.id,
    )
    db.add(payout)
    db.flush()
    payout.payout_code = _payout_code(payout.id)

    for c in conversions:
        c.status = "paid"

    db.commit()
    db.refresh(payout)

    aff = db.query(Affiliate).filter(Affiliate.id == data.affiliate_id).first()
    if aff and aff.user_id:
        enqueue_notification(db, user_id=aff.user_id, notification_type="affiliate_payout", title="Payout Processed", message=f"Your affiliate payout of {total} {payout.currency} has been initiated.", entity_type="affiliate_payout", entity_id=payout.id)
        db.commit()

    return _s_payout(payout)


def list_payouts(db: Session, affiliate_id: Optional[int] = None, page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliatePayout)
    if affiliate_id:
        q = q.filter(AffiliatePayout.affiliate_id == affiliate_id)
    q = q.order_by(AffiliatePayout.id.desc())
    total = q.count()
    items = [_s_payout(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}
