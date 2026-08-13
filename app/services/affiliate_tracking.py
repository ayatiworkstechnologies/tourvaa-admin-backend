import re
import secrets
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models.affiliate_tracking import (
    AffiliateClick,
    AffiliateConversion,
    AffiliateLink,
    AffiliatePayout,
    AffiliatePayoutItem,
    AffiliateWalletTransaction,
)
from app.schemas.affiliate_tracking import AffiliateLinkCreate, AffiliateLinkUpdate, AffiliatePayoutCreate
from app.models.affiliates import Affiliate
from app.utils.money import money, utcnow
from app.services.affiliate_commission import compute_commission
from app.services.audit import log_audit
from app.services.notifications import enqueue_notification
from app.models.users import User


def _ref_code() -> str:
    return secrets.token_urlsafe(12).upper()


def _payout_code(payout_id: int) -> str:
    return f"AFF-PAY-{payout_id:06d}"


def is_affiliate_user(user: Optional[User]) -> bool:
    slug = (getattr(getattr(user, "role", None), "slug", "") or "").lower()
    return slug == "affiliate"


def get_actor_affiliate(db: Session, user: User) -> Affiliate:
    aff = db.query(Affiliate).filter(Affiliate.user_id == user.id).first()
    if not aff:
        raise HTTPException(status_code=403, detail="Affiliate profile not found")
    return aff


def ensure_affiliate_access(db: Session, affiliate_id: int, user: Optional[User]) -> None:
    """Scope affiliate-portal callers to their own affiliate_id.

    Mirrors ensure_agent_customer_access's pattern: admins/staff reach this
    via a coarse affiliates.view permission check and are not further
    restricted here, but a logged-in affiliate is - so an affiliate can't
    read another affiliate's links/clicks/conversions/commissions/payouts by
    changing the affiliate_id in the URL.
    """
    if not is_affiliate_user(user):
        return
    aff = db.query(Affiliate).filter(Affiliate.user_id == user.id).first()
    if not aff or aff.id != affiliate_id:
        raise HTTPException(status_code=403, detail="Affiliate access denied")


def _s_link(r: AffiliateLink) -> dict:
    return {
        "id": r.id, "affiliate_id": r.affiliate_id, "ref_code": r.ref_code, "custom_alias": r.custom_alias,
        "link_type": r.link_type, "tour_id": r.tour_id, "tour_title": r.tour.title if r.tour_id and r.tour else None,
        "destination_url": r.destination_url,
        "label": r.label, "campaign_name": r.campaign_name,
        "utm_source": r.utm_source, "utm_medium": r.utm_medium, "utm_campaign": r.utm_campaign, "utm_content": r.utm_content, "utm_term": r.utm_term,
        "commission_type_override": r.commission_type_override,
        "commission_percentage_override": str(r.commission_percentage_override) if r.commission_percentage_override is not None else None,
        "commission_fixed_override": str(r.commission_fixed_override) if r.commission_fixed_override is not None else None,
        "attribution_model": r.attribution_model, "attribution_window_days": r.attribution_window_days,
        "valid_from": r.valid_from, "valid_until": r.valid_until,
        "status": r.status, "is_active": r.status == "active",
        "total_clicks": len(r.clicks), "total_conversions": len(r.conversions),
        "created_by": r.created_by, "updated_by": r.updated_by,
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


def _s_click(r: AffiliateClick) -> dict:
    return {"id": r.id, "link_id": r.link_id, "affiliate_id": r.affiliate_id, "ip_address": r.ip_address, "referrer": r.referrer, "clicked_at": r.clicked_at}


def _s_conversion(r: AffiliateConversion) -> dict:
    return {
        "id": r.id, "link_id": r.link_id, "affiliate_id": r.affiliate_id, "booking_id": r.booking_id,
        "booking_code": r.booking.booking_code if r.booking else None,
        "commission_rule_id": r.commission_rule_id,
        "booking_amount": str(r.booking_amount), "eligible_amount": str(r.eligible_amount),
        "commission_percentage": str(r.commission_percentage), "commission_amount": str(r.commission_amount),
        "original_commission": str(r.original_commission) if r.original_commission is not None else None,
        "adjustment_amount": str(r.adjustment_amount), "final_commission": str(r.final_commission) if r.final_commission is not None else None,
        "currency": r.currency, "status": r.status,
        "approved_at": r.approved_at, "available_at": r.available_at, "converted_at": r.converted_at,
    }


def _wallet_entry(db: Session, *, affiliate_id: int, transaction_type: str, amount, currency: str = "USD", commission_id: Optional[int] = None, payout_id: Optional[int] = None, reference_type: Optional[str] = None, reference_id: Optional[int] = None, description: Optional[str] = None) -> AffiliateWalletTransaction:
    entry = AffiliateWalletTransaction(
        affiliate_id=affiliate_id, commission_id=commission_id, payout_id=payout_id,
        transaction_type=transaction_type, amount=money(amount), currency=currency,
        reference_type=reference_type, reference_id=reference_id, description=description,
    )
    db.add(entry)
    db.flush()
    return entry


def _s_payout(r: AffiliatePayout) -> dict:
    return {"id": r.id, "payout_code": r.payout_code, "affiliate_id": r.affiliate_id, "total_amount": str(r.total_amount), "currency": r.currency, "payment_method": r.payment_method, "reference_number": r.reference_number, "status": r.status, "notes": r.notes, "paid_at": r.paid_at, "created_at": r.created_at}


# links

RESERVED_ALIASES = {"admin", "api", "r", "login", "logout", "register", "affiliate", "affiliates", "static", "storage", "auth", "www"}
_ALIAS_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,59}$")


def _normalize_alias(alias: Optional[str]) -> Optional[str]:
    if not alias:
        return None
    normalized = alias.strip().lower()
    if not _ALIAS_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Alias must be 3-60 lowercase letters, numbers or hyphens")
    if normalized in RESERVED_ALIASES:
        raise HTTPException(status_code=400, detail="This alias is reserved")
    return normalized


def _ensure_alias_available(db: Session, alias: str, exclude_link_id: Optional[int] = None) -> None:
    q = db.query(AffiliateLink).filter((AffiliateLink.ref_code == alias.upper()) | (AffiliateLink.custom_alias == alias))
    if exclude_link_id:
        q = q.filter(AffiliateLink.id != exclude_link_id)
    if q.first():
        raise HTTPException(status_code=409, detail="This alias is already in use")


def _apply_link_fields(link: AffiliateLink, data: AffiliateLinkCreate, *, tour, is_admin: bool) -> None:
    link.destination_url = data.destination_url
    link.label = data.label
    link.campaign_name = data.campaign_name
    link.utm_source = data.utm_source
    link.utm_medium = data.utm_medium
    link.utm_campaign = data.utm_campaign
    link.utm_content = data.utm_content
    link.utm_term = data.utm_term
    # Commission overrides, attribution model/window, and validity dates are
    # admin-only even at creation time - a self-service caller's create
    # payload silently drops these rather than erroring, matching how
    # update_link ignores (not rejects) admin-only fields for self-service.
    if is_admin:
        link.commission_type_override = data.commission_type_override
        link.commission_percentage_override = data.commission_percentage_override
        link.commission_fixed_override = data.commission_fixed_override
        link.attribution_model = data.attribution_model or "last_click"
        link.attribution_window_days = data.attribution_window_days or 30
        link.valid_from = data.valid_from
        link.valid_until = data.valid_until
    else:
        link.attribution_model = "last_click"
        link.attribution_window_days = 30


def create_link(db: Session, affiliate_id: int, data: AffiliateLinkCreate, actor: User, *, is_admin: bool = True) -> dict:
    from app.models.cms import Tour

    aff = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not aff:
        raise HTTPException(status_code=404, detail="Affiliate not found")

    tour = None
    link_type = (data.link_type or "custom").lower()
    if link_type == "tour":
        if not data.tour_id:
            raise HTTPException(status_code=400, detail="tour_id is required for TOUR links")
        tour = db.query(Tour).filter(Tour.id == data.tour_id, Tour.status == "published").first()
        if not tour:
            raise HTTPException(status_code=400, detail="Tour not found or not published")

    alias = _normalize_alias(data.custom_alias)
    if alias:
        _ensure_alias_available(db, alias)

    link = AffiliateLink(affiliate_id=affiliate_id, ref_code=_ref_code(), link_type=link_type, tour_id=tour.id if tour else None, custom_alias=alias, status="active", created_by=getattr(actor, "id", None))
    _apply_link_fields(link, data, tour=tour, is_admin=is_admin)
    db.add(link)
    db.commit()
    db.refresh(link)
    log_audit(db, actor=actor, action="create_affiliate_link", entity_type="affiliate_link", entity_id=link.id, new_values=_s_link(link))
    db.commit()
    return _s_link(link)


def get_link(db: Session, link_id: int) -> AffiliateLink:
    link = db.query(AffiliateLink).filter(AffiliateLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Affiliate link not found")
    return link


def list_links(db: Session, affiliate_id: int) -> list:
    return [_s_link(r) for r in db.query(AffiliateLink).filter(AffiliateLink.affiliate_id == affiliate_id).order_by(AffiliateLink.id.desc()).all()]


def list_links_admin(db: Session, *, affiliate_id: Optional[int] = None, tour_id: Optional[int] = None, status: str = "", search: str = "", page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliateLink)
    if affiliate_id:
        q = q.filter(AffiliateLink.affiliate_id == affiliate_id)
    if tour_id:
        q = q.filter(AffiliateLink.tour_id == tour_id)
    if status:
        q = q.filter(AffiliateLink.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter((AffiliateLink.ref_code.ilike(like)) | (AffiliateLink.custom_alias.ilike(like)) | (AffiliateLink.campaign_name.ilike(like)) | (AffiliateLink.label.ilike(like)))
    q = q.order_by(AffiliateLink.id.desc())
    total = q.count()
    items = [_s_link(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def update_link(db: Session, link_id: int, data: AffiliateLinkUpdate, actor: User, *, is_admin: bool) -> dict:
    """Self-service callers may only touch campaign/UTM/label/destination
    fields (enforced here, not just by omission in the frontend) - commission
    overrides, attribution window, validity and status stay admin-only per
    spec section 51 ("affiliate cannot change commission / attribution rules
    / admin-disabled link state")."""
    link = get_link(db, link_id)
    old = _s_link(link)
    updates = data.model_dump(exclude_unset=True)

    self_service_fields = {"label", "destination_url", "campaign_name", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}
    admin_only_fields = {"commission_type_override", "commission_percentage_override", "commission_fixed_override", "attribution_model", "attribution_window_days", "valid_from", "valid_until", "status"}

    if not is_admin:
        updates = {k: v for k, v in updates.items() if k in self_service_fields}
        if updates.get("destination_url") is not None and link.status == "disabled":
            raise HTTPException(status_code=403, detail="This link was disabled by admin and cannot be edited")

    if is_admin and "status" in updates:
        new_status = updates.pop("status")
        if new_status is not None:
            _transition_link_status(link, new_status)

    for key, value in updates.items():
        setattr(link, key, value)
    link.updated_by = getattr(actor, "id", None)

    db.commit()
    db.refresh(link)
    log_audit(db, actor=actor, action="update_affiliate_link", entity_type="affiliate_link", entity_id=link.id, old_values=old, new_values=_s_link(link))
    db.commit()
    return _s_link(link)


_LINK_STATUS_TRANSITIONS = {
    "draft": {"active"},
    "active": {"disabled", "expired"},
    "disabled": {"active"},
    "expired": {"active"},
}


def _transition_link_status(link: AffiliateLink, new_status: str) -> None:
    if new_status == link.status:
        return
    allowed = _LINK_STATUS_TRANSITIONS.get(link.status, set())
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Cannot move link from '{link.status}' to '{new_status}'")
    link.status = new_status


def activate_link(db: Session, link_id: int, actor: User) -> dict:
    link = get_link(db, link_id)
    old = _s_link(link)
    if link.affiliate and (link.affiliate.status or "").lower() != "active":
        raise HTTPException(status_code=400, detail="Affiliate is not active")
    if link.link_type == "tour" and link.tour_id:
        from app.models.cms import Tour
        tour = db.query(Tour).filter(Tour.id == link.tour_id).first()
        if not tour or tour.status != "published":
            raise HTTPException(status_code=400, detail="Tour is not published")
    _transition_link_status(link, "active")
    link.updated_by = actor.id
    db.commit()
    db.refresh(link)
    log_audit(db, actor=actor, action="activate_affiliate_link", entity_type="affiliate_link", entity_id=link.id, old_values=old, new_values=_s_link(link))
    db.commit()
    return _s_link(link)


def disable_link(db: Session, link_id: int, actor: User) -> dict:
    """Existing clicks/bookings/commissions are untouched; future clicks stop
    creating attribution but the URL keeps redirecting (spec section 21/95)."""
    link = get_link(db, link_id)
    old = _s_link(link)
    _transition_link_status(link, "disabled")
    link.updated_by = actor.id
    db.commit()
    db.refresh(link)
    log_audit(db, actor=actor, action="disable_affiliate_link", entity_type="affiliate_link", entity_id=link.id, old_values=old, new_values=_s_link(link))
    db.commit()
    return _s_link(link)


def duplicate_link(db: Session, link_id: int, actor: User, *, campaign_name: Optional[str] = None) -> dict:
    """Copies safe configuration onto a fresh short_code; never copies
    clicks/bookings/commissions (spec section 23)."""
    source = get_link(db, link_id)
    clone = AffiliateLink(
        affiliate_id=source.affiliate_id, ref_code=_ref_code(), link_type=source.link_type, tour_id=source.tour_id,
        destination_url=source.destination_url, label=source.label,
        campaign_name=campaign_name if campaign_name is not None else source.campaign_name,
        utm_source=source.utm_source, utm_medium=source.utm_medium, utm_campaign=source.utm_campaign, utm_content=source.utm_content, utm_term=source.utm_term,
        commission_type_override=source.commission_type_override, commission_percentage_override=source.commission_percentage_override, commission_fixed_override=source.commission_fixed_override,
        attribution_model=source.attribution_model, attribution_window_days=source.attribution_window_days,
        valid_from=source.valid_from, valid_until=source.valid_until,
        status="active", created_by=getattr(actor, "id", None),
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    log_audit(db, actor=actor, action="duplicate_affiliate_link", entity_type="affiliate_link", entity_id=clone.id, old_values={"source_link_id": source.id}, new_values=_s_link(clone))
    db.commit()
    return _s_link(clone)


def delete_link(db: Session, link_id: int, actor: User) -> dict:
    """Soft-deletes if there's any historical data (clicks/bookings/commissions);
    hard-deletes an untouched draft/never-clicked link."""
    link = get_link(db, link_id)
    old = _s_link(link)
    has_history = bool(link.clicks) or bool(link.conversions)
    if has_history:
        link.status = "deleted"
        link.deleted_at = utcnow()
        link.updated_by = getattr(actor, "id", None)
        db.commit()
        log_audit(db, actor=actor, action="soft_delete_affiliate_link", entity_type="affiliate_link", entity_id=link.id, old_values=old, new_values=_s_link(link))
        db.commit()
        return {"deleted": True, "soft": True}
    log_audit(db, actor=actor, action="delete_affiliate_link", entity_type="affiliate_link", entity_id=link.id, old_values=old)
    db.delete(link)
    db.commit()
    return {"deleted": True, "soft": False}


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
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def list_conversions(db: Session, affiliate_id: int, page: int = 1, limit: int = 20) -> dict:
    q = db.query(AffiliateConversion).filter(AffiliateConversion.affiliate_id == affiliate_id).order_by(AffiliateConversion.id.desc())
    total = q.count()
    items = [_s_conversion(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def resolve_affiliate_link(db: Session, ref_code: str) -> Optional[AffiliateLink]:
    if not ref_code:
        return None
    return db.query(AffiliateLink).filter(AffiliateLink.ref_code == ref_code, AffiliateLink.is_active == True).first()


def resolve_attribution_from_request(db: Session, request: Optional[Request]):
    """Look up the caller's server-tracked attribution (set by GET /r/{code})
    from the tourvaa_affiliate_ref cookie. Used as the fallback source of
    affiliate attribution for a booking when the client doesn't explicitly
    pass affiliate_ref_code (e.g. the customer clicked a link minutes/days
    earlier, then books later without the ref_code in the create-booking
    payload). Never raises - a missing/invalid/expired cookie just means no
    affiliate attribution, which is the normal, expected case for most
    bookings.
    """
    from app.models.affiliate_tracking import AffiliateAttribution

    if not request:
        return None
    token = request.cookies.get("tourvaa_affiliate_ref")
    if not token:
        return None
    now = utcnow()
    attribution = (
        db.query(AffiliateAttribution)
        .filter(AffiliateAttribution.visitor_id == token, AffiliateAttribution.status == "active", AffiliateAttribution.expires_at > now)
        .order_by(AffiliateAttribution.attributed_at.desc())
        .first()
    )
    if not attribution:
        return None
    aff = db.query(Affiliate).filter(Affiliate.id == attribution.affiliate_id).first()
    if not aff or (aff.status or "").lower() != "active":
        return None
    return attribution


def record_conversion(db: Session, *, ref_code: str, booking_id: int, booking_amount: Decimal, currency: str = "USD") -> Optional[AffiliateConversion]:
    """Called from booking service when a booking is confirmed and has a ref_code.

    Idempotent by booking_id (unique column + explicit pre-check) so a
    payment callback firing twice - or the confirm path running both in
    bookings.py's supplier-accept branch and payments.py's payment-sync
    branch - never creates two commissions for the same booking (spec's
    duplicate-commission-protection requirement).
    """
    link = resolve_affiliate_link(db, ref_code)
    if not link:
        return None
    aff = db.query(Affiliate).filter(Affiliate.id == link.affiliate_id).first()
    if not aff:
        return None

    existing = db.query(AffiliateConversion).filter(AffiliateConversion.booking_id == booking_id).first()
    if existing:
        return existing

    eligible_amount = money(booking_amount)
    calc = compute_commission(db, affiliate=aff, link=link, eligible_amount=eligible_amount)

    conversion = AffiliateConversion(
        link_id=link.id,
        affiliate_id=link.affiliate_id,
        booking_id=booking_id,
        commission_rule_id=calc["commission_rule_id"],
        booking_amount=eligible_amount,
        eligible_amount=eligible_amount,
        commission_percentage=calc["commission_percentage"],
        commission_amount=calc["commission_amount"],
        original_commission=calc["commission_amount"],
        adjustment_amount=money(0),
        final_commission=calc["commission_amount"],
        currency=currency,
        status="pending",
    )
    db.add(conversion)
    db.flush()

    _wallet_entry(
        db, affiliate_id=aff.id, transaction_type="COMMISSION_CREDIT", amount=conversion.final_commission,
        currency=currency, commission_id=conversion.id, reference_type="booking", reference_id=booking_id,
        description=f"Commission for booking #{booking_id}",
    )
    if aff.user_id:
        enqueue_notification(
            db, user_id=aff.user_id, notification_type="affiliate_commission_created", title="New Referral Booking",
            message=f"You earned a commission of {conversion.final_commission} {currency} on booking #{booking_id}.",
            entity_type="affiliate_conversion", entity_id=conversion.id,
        )
    return conversion


def reverse_conversion(db: Session, booking_id: int, *, refund_amount: Optional[Decimal] = None, refund_percentage: Optional[Decimal] = None) -> Optional[AffiliateConversion]:
    """Void or proportionally adjust a booking's affiliate commission on cancellation/refund.

    Called with no refund info for a full cancellation (voids the whole
    commission). Called with refund_amount/refund_percentage for a partial
    refund on an otherwise-standing booking - reduces final_commission
    proportionally instead of wiping it out, and never rewrites
    original_commission so the pre-adjustment figure stays auditable.

    A conversion already marked paid represents money that has actually left
    the business to the affiliate - reversing/adjusting it doesn't claw that
    back automatically, so paid conversions are left alone (same principle as
    the supplier ledger: reversal only applies to unsettled commission).
    """
    conversion = db.query(AffiliateConversion).filter(AffiliateConversion.booking_id == booking_id).with_for_update().first()
    if not conversion or conversion.status in ("paid", "void", "reversed"):
        return conversion

    original = money(conversion.original_commission if conversion.original_commission is not None else conversion.commission_amount)

    is_full = refund_amount is None and refund_percentage is None
    if not is_full and refund_percentage is not None:
        is_full = money(refund_percentage) >= 100
    elif not is_full and refund_amount is not None and conversion.eligible_amount:
        is_full = money(refund_amount) >= money(conversion.eligible_amount)

    if is_full:
        new_final = money(0)
        conversion.status = "void"
    else:
        if refund_percentage is not None:
            remaining_ratio = (money(100) - money(refund_percentage)) / Decimal(100)
        else:
            remaining_amount = max(money(0), money(conversion.eligible_amount) - money(refund_amount))
            remaining_ratio = (remaining_amount / conversion.eligible_amount) if conversion.eligible_amount else Decimal(0)
        new_final = money(original * remaining_ratio)
        # status is left as-is (pending/confirmed) - a partial refund doesn't
        # change where the booking is in its own lifecycle, only how much
        # commission is ultimately owed.

    adjustment = money(new_final - original)
    conversion.adjustment_amount = money(conversion.adjustment_amount or 0) + adjustment
    conversion.final_commission = new_final
    conversion.commission_amount = new_final
    db.flush()

    if adjustment != 0:
        _wallet_entry(
            db, affiliate_id=conversion.affiliate_id, transaction_type="COMMISSION_ADJUSTMENT", amount=adjustment,
            currency=conversion.currency, commission_id=conversion.id, reference_type="booking", reference_id=booking_id,
            description=("Commission voided - booking cancelled" if is_full else "Commission adjusted for partial refund"),
        )
        aff = db.query(Affiliate).filter(Affiliate.id == conversion.affiliate_id).first()
        if aff and aff.user_id:
            notif_type = "affiliate_commission_voided" if is_full else "affiliate_commission_adjusted"
            title = "Commission Voided" if is_full else "Commission Adjusted"
            enqueue_notification(
                db, user_id=aff.user_id, notification_type=notif_type, title=title,
                message=f"Your commission for booking #{booking_id} was {'voided' if is_full else 'adjusted'}. New amount: {new_final} {conversion.currency}.",
                entity_type="affiliate_conversion", entity_id=conversion.id,
            )

    return conversion


# commission summary

def get_commissions(db: Session, affiliate_id: int) -> dict:
    rows = db.query(AffiliateConversion).filter(AffiliateConversion.affiliate_id == affiliate_id).all()
    live_rows = [r for r in rows if r.status not in ("void", "reversed")]
    total_commission = sum(money(r.commission_amount) for r in live_rows)
    pending = sum(money(r.commission_amount) for r in rows if r.status == "pending")
    confirmed = sum(money(r.commission_amount) for r in rows if r.status == "confirmed")
    available = sum(money(r.commission_amount) for r in rows if r.status == "available")
    paid = sum(money(r.commission_amount) for r in rows if r.status == "paid")
    void = sum(money(r.commission_amount) for r in rows if r.status in ("void", "reversed"))
    return {
        "affiliate_id": affiliate_id,
        "total_conversions": len(rows),
        "total_commission": str(total_commission),
        "pending_commission": str(pending),
        "confirmed_commission": str(confirmed),
        "available_commission": str(available),
        "paid_commission": str(paid),
        "void_commission": str(void),
        "entries": [_s_conversion(r) for r in rows],
    }


# payouts

def create_payout(db: Session, data: AffiliatePayoutCreate, actor: User) -> dict:
    if not data.conversion_ids:
        raise HTTPException(status_code=400, detail="No conversions specified")

    # Lock the requested rows before deciding what's payable so two
    # concurrent payout requests for the same conversions can't both read
    # them as "pending" and each create a payout - the second transaction
    # blocks here until the first commits, then sees the now-"paid" status
    # and rejects instead of double-paying.
    conversions = (
        db.query(AffiliateConversion)
        .filter(
            AffiliateConversion.id.in_(data.conversion_ids),
            AffiliateConversion.affiliate_id == data.affiliate_id,
        )
        .with_for_update()
        .all()
    )
    found_ids = {c.id for c in conversions}
    missing_ids = sorted(set(data.conversion_ids) - found_ids)
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Conversions not found for this affiliate: {missing_ids}")

    unpayable_ids = sorted(c.id for c in conversions if c.status not in ("pending", "confirmed"))
    if unpayable_ids:
        raise HTTPException(status_code=409, detail=f"Conversions already paid or reversed: {unpayable_ids}")

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
    payout.paid_at = utcnow()

    for c in conversions:
        c.status = "paid"
        db.add(AffiliatePayoutItem(payout_id=payout.id, conversion_id=c.id, amount=c.final_commission if c.final_commission is not None else c.commission_amount))

    _wallet_entry(
        db, affiliate_id=data.affiliate_id, transaction_type="PAYOUT_DEBIT", amount=-total,
        currency=payout.currency, payout_id=payout.id, reference_type="affiliate_payout", reference_id=payout.id,
        description=f"Payout {payout.payout_code}",
    )

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
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}
