import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.services.audit import log_audit
from app.services.payments import serialize_payment
from app.models.bookings import (
    Booking,
    BookingAccommodation,
    BookingCommunication,
    BookingExtension,
    BookingOptionalActivity,
    BookingStatusHistory,
    BookingTraveller,
)
from app.schemas.bookings import (
    AssignSupplierRequest,
    BookingAddonPayload,
    BookingCancelRequest,
    BookingCommunicationCreate,
    BookingCreate,
    BookingStatusUpdate,
    BookingTravelDateUpdate,
    BookingUpdate,
    SupplierDecisionRequest,
    SupplierDueDateUpdate,
)
from app.models.cms import City, Country, Tour
from app.utils.money import apply_markup, as_aware_utc, money, money_str, utcnow
from app.services.settings import (
    get_allow_agent_markup,
    get_default_deposit_cutoff_days,
    get_default_deposit_percentage,
)
from app.models.customers import Customer
from app.models.agents import Agent
from app.models.suppliers import Supplier
from app.models.supplier_ledger import SupplierLedger, SupplierPayout, SupplierPayoutItem
from app.models.tours import TourAccommodationExtra, TourCalendar, TourDatePrice, TourDiscount, TourExtension, TourGroupDiscountTier, TourOptionalActivity, TourPricing, TourUnavailableDate
from app.models.users import User

logger = logging.getLogger(__name__)


def _do_send_booking_email(db, key: str, values: dict, fallback_subject: str, fallback_html: str, to_email: str) -> None:
    from app.utils.email_templates import render_database_email
    from app.utils.mailer import try_send_email
    try:
        subject, html = render_database_email(db, key, values, fallback_subject, fallback_html)
        try_send_email(to_email, subject, html, template_key=key)
    except Exception as exc:
        logger.warning("Booking email %s to %s failed: %s", key, to_email, exc)


def _send_booking_email(db, key: str, values: dict, fallback_subject: str, fallback_html: str, to_email: str, background_tasks: BackgroundTasks | None = None):
    # Booking success must never depend on (or wait on) email delivery - the
    # actual send is scheduled via BackgroundTasks (or a daemon thread when
    # none is available) rather than run inline. See
    # app.utils.mailer.dispatch_email_task for how each mode stays safe.
    from app.utils.mailer import dispatch_email_task
    dispatch_email_task(background_tasks, db, _do_send_booking_email, key, values, fallback_subject, fallback_html, to_email)


def _do_email_admins_booking_event(db, event_title: str, detail: str, booking_id: int, booking_code: str, tour_name: str | None) -> None:
    from app.utils.email_templates import admin_booking_event_email
    from app.utils.notification_triggers import email_admins
    admin_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking_id}"
    email_admins(
        db, "admin_booking_event",
        {"event_title": event_title, "detail": detail, "booking_code": booking_code,
         "tour_name": tour_name, "admin_url": admin_url, "button_text": "View booking", "button_url": admin_url},
        f"{event_title} - {booking_code}",
        admin_booking_event_email(event_title, detail, booking_code, tour_name, admin_url),
    )


def _email_admins_booking_event(db, event_title: str, detail: str, booking: Booking, background_tasks: BackgroundTasks | None = None) -> None:
    from app.utils.mailer import dispatch_email_task
    dispatch_email_task(
        background_tasks, db, _do_email_admins_booking_event,
        event_title, detail, booking.id, booking.booking_code, booking.tour_name,
    )


def _email_agent_booking_status(db, booking: Booking, new_status: str, reason: str) -> None:
    if not (booking.agent and booking.agent.user and booking.agent.user.email):
        return
    from app.utils.email_templates import booking_status_update_email
    portal_url = f"{settings.FRONTEND_URL}/agent/bookings/{booking.id}"
    _send_booking_email(
        db, "booking_status_update",
        {"name": booking.agent.agent_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
         "new_status": new_status.replace("_", " ").title(), "reason": reason or "", "login_url": portal_url,
         "button_text": "View booking", "button_url": portal_url},
        f"Booking update - {booking.booking_code}",
        booking_status_update_email(booking.agent.agent_name, booking.booking_code, booking.tour_name, new_status, reason or "", portal_url),
        booking.agent.user.email,
    )


def _booking_code(db: Session, booking_id: int, source: str = "customer") -> str:
    from app.services.settings import get_booking_prefix

    prefix = get_booking_prefix(db)
    return f"{prefix}{'A' if source == 'agent' else 'C'}-{booking_id}"


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date '{value}' - use YYYY-MM-DD")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _resolve_date_price(db: Session, tour_id: int | None, date_value):
    """Seasonal/peak-date override: if an active TourDatePrice row exists for
    this exact departure date, its adult_price/child_price are used verbatim
    as the final customer-facing per-person price for that date, taking
    priority over the pax-count slab (see TourDatePrice docstring)."""
    if not tour_id or not date_value:
        return None
    if isinstance(date_value, str):
        parsed = _parse_dt(date_value)
        if not parsed:
            return None
        target_date = parsed.date()
    else:
        target_date = date_value.date() if hasattr(date_value, "date") else date_value
    return db.query(TourDatePrice).filter(TourDatePrice.tour_id == tour_id, TourDatePrice.price_date == target_date, TourDatePrice.status == "active").first()


def _mask_passport(value: str | None) -> str | None:
    if not value:
        return value
    return "*" * max(len(value) - 4, 0) + value[-4:]


def _user_role(user: User | None) -> str:
    if not user:
        return "admin"
    role_slugs = []
    if user.role and user.role.slug:
        role_slugs.append(user.role.slug.lower())
    role_slugs.extend(
        user_role.role.slug.lower()
        for user_role in (getattr(user, "user_roles", None) or [])
        if user_role.role and user_role.role.slug
    )
    user_type = str(getattr(user, "user_type", "") or "").lower()
    if user_type == "supplier" or any("supplier" in slug for slug in role_slugs):
        return "supplier"
    if user_type == "agent" or any("agent" in slug for slug in role_slugs):
        return "agent"
    if user_type == "customer" or any("customer" in slug for slug in role_slugs):
        return "customer"
    return "admin"


def _ensure_booking_access(booking: Booking, actor: User | None) -> None:
    role = _user_role(actor)
    if role == "admin" or actor is None:
        return
    if role == "supplier" and booking.supplier and booking.supplier.user_id == actor.id:
        return
    if role == "agent" and booking.agent and booking.agent.user_id == actor.id:
        return
    if role == "customer" and booking.customer and booking.customer.user_id == actor.id:
        return
    raise HTTPException(status_code=403, detail="Booking access denied")


def _history(db: Session, booking: Booking, old_status: str | None, new_status: str, actor: User | None, source: str, reason: str | None = None, metadata: dict | None = None):
    db.add(BookingStatusHistory(
        booking_id=booking.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_user_id=actor.id if actor else None,
        change_source=source,
        reason=reason,
        metadata_json=metadata,
    ))


def _set_status(db: Session, booking: Booking, new_status: str, actor: User | None, source: str, reason: str | None = None, metadata: dict | None = None):
    old_status = booking.booking_status
    booking.booking_status = new_status
    if old_status != new_status:
        _history(db, booking, old_status, new_status, actor, source, reason, metadata)


BOOKING_STATUS_TRANSITIONS = {
    "draft": {"pending_payment", "pending_credit_approval", "pending_supplier_assignment", "cancelled"},
    "pending_payment": {"pending_credit_approval", "payment_authorized", "pending_supplier_assignment", "pending_supplier_acceptance", "confirmed", "cancellation_requested", "cancelled", "declined"},
    "pending_credit_approval": {"pending_payment", "payment_authorized", "pending_supplier_assignment", "cancellation_requested", "cancelled", "declined"},
    "pending_supplier_assignment": {"pending_payment", "payment_authorized", "pending_supplier_acceptance", "supplier_reassignment_required", "cancellation_requested", "cancelled", "declined"},
    "payment_authorized": {"pending_supplier_assignment", "pending_supplier_acceptance", "confirmed", "cancellation_requested", "cancelled", "declined"},
    "pending_supplier_acceptance": {"pending_supplier_assignment", "supplier_reassignment_required", "confirmed", "postponed", "cancellation_requested", "cancelled", "declined"},
    "supplier_reassignment_required": {"pending_supplier_assignment", "pending_supplier_acceptance", "cancellation_requested", "cancelled", "declined"},
    "confirmed": {"ready_to_travel", "ongoing", "completed", "postponed", "supplier_reassignment_required", "cancellation_requested", "cancelled"},
    "ready_to_travel": {"ongoing", "completed", "postponed", "cancellation_requested", "cancelled"},
    "upcoming": {"confirmed", "ready_to_travel", "ongoing", "completed", "postponed", "cancellation_requested", "cancelled"},
    "ongoing": {"completed", "postponed", "supplier_reassignment_required", "cancellation_requested", "cancelled"},
    "postponed": {"confirmed", "ready_to_travel", "ongoing", "completed", "cancellation_requested", "cancelled"},
    "cancellation_requested": {"pending_payment", "payment_authorized", "pending_supplier_acceptance", "confirmed", "ready_to_travel", "ongoing", "postponed", "cancelled"},
    "cancelled": {"refunded"},
    "declined": {"pending_supplier_assignment", "supplier_reassignment_required", "refunded"},
    "completed": set(),
    "refunded": set(),
}


def _validate_booking_status_transition(current_status: str, target_status: str) -> bool:
    current = (current_status or "").strip().lower()
    target = (target_status or "").strip().lower()
    if current == target:
        return False
    allowed = BOOKING_STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        allowed_text = ", ".join(sorted(allowed)) or "none (terminal status)"
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change booking status from {current or 'unknown'} to {target}. Allowed next statuses: {allowed_text}",
        )
    return True


def _booking_seat_count(booking: Booking) -> int:
    adults = booking.adults_count if booking.adults_count is not None else booking.no_of_adults
    children = booking.children_count if booking.children_count is not None else booking.no_of_children
    return max(0, int(adults or 0) + int(children or 0))


def _similar_tours_for_email(db: Session, tour_id: int | None, limit: int = 3) -> list[dict]:
    """{title, url} pairs for a declined booking's email - same TourSimilar
    linkage public.py's tour detail page already uses."""
    if not tour_id:
        return []
    from app.models.tours import TourSimilar
    from app.schemas.cms import slugify

    links = db.query(TourSimilar).filter(TourSimilar.tour_id == tour_id).limit(limit).all()
    results = []
    for link in links:
        st = db.query(Tour).filter(Tour.id == link.similar_tour_id, Tour.status == "published").first()
        if st:
            country_slug = slugify(st.country.country_name if st.country else "worldwide")
            results.append({"title": st.title, "url": f"{settings.FRONTEND_URL}/tours/{country_slug}/{st.slug}"})
    return results


def _legacy_affiliate_eligible_amount(booking: Booking):
    """Pre-snapshot fallback: customer amount net of tax, fees and agent
    markup. Only used for bookings created before commission_base_amount
    existed."""
    if booking.booking_source == "agent" and booking.agent_net_price:
        gross = money(booking.agent_net_price)
    else:
        gross = money(booking.final_amount or booking.total_cost or 0)
    eligible = gross - money(booking.tax_amount or 0) - money(booking.surcharge_amount or 0)
    return max(money(0), eligible)


def affiliate_eligible_amount(booking: Booking):
    """Base amount for affiliate commission: the booking's snapshotted
    commission base (tour selling amount after the supplier's share of
    discounts, excluding tax, service fee, gateway fee, agent markup and
    non-commissionable/cost-plus add-ons) -- the same base Tourvaa's own
    commission is computed on, so an affiliate rate below Tourvaa's rate can
    never exceed Tourvaa's commission. Refund-time proration is handled
    separately by affiliate_tracking.reverse_conversion."""
    if booking.commission_base_amount is not None:
        return money(booking.commission_base_amount)
    return _legacy_affiliate_eligible_amount(booking)


def _supplier_discount_share(amount, funded_by) -> Decimal:
    """Portion of a discount the supplier absorbs: all of it (SUPPLIER, the
    default and legacy behaviour), none (TOURVAA) or half (SHARED)."""
    amount = money(amount or 0)
    mode = (funded_by or "SUPPLIER").upper()
    if mode == "TOURVAA":
        return money(0)
    if mode == "SHARED":
        return money(amount / money(2))
    return amount


def compute_booking_financial_split(
    *,
    base_amount,
    group_discount_amount=0,
    group_discount_funded_by=None,
    promo_discount_amount=0,
    promo_discount_funded_by=None,
    addon_total=0,
    non_commissionable_addon_amount=0,
    cost_plus_customer_amount=0,
    cost_plus_supplier_payable=0,
    commission_percentage=0,
    supplier_base_amount=None,
) -> dict:
    """Pure supplier/Tourvaa money split for one booking, from amounts that
    were all resolved at pricing time (never from the tour's live slab).

    base_amount is the traveller amount actually charged (adult + child at
    the resolved storefront price -- supplier price plus Tourvaa's admin
    markup -- plus infants and single supplement). supplier_base_amount is
    the same traveller amount at the supplier's own prices (None = no
    markup, i.e. equal to base_amount). The difference is Tourvaa's markup.
    Tax, service fee, gateway fee and agent markup are deliberately NOT
    inputs: they are customer-side buckets and never reach the supplier or
    the commission base.

    Discounts are charged against the storefront price. The supplier-side
    part of each discount is its share of the supplier price
    (discount * supplier_base / base), split per funded_by as before; the
    rest (the part that came off the markup) and any Tourvaa-funded part
    is absorbed by Tourvaa. So a 10% SUPPLIER-funded discount cuts both the
    customer price and the supplier's price by 10%, and with no markup this
    reduces exactly to the previous behaviour.

    Invariant (when nothing is clamped at 0):
      supplier_net_payable + tourvaa_gross_revenue
        == base - group - promo + add-ons      (= final - tax - fees)
    """
    base_amount = money(base_amount or 0)
    supplier_base = money(supplier_base_amount) if supplier_base_amount is not None else base_amount
    group = money(group_discount_amount or 0)
    promo = money(promo_discount_amount or 0)
    addons = money(addon_total or 0)
    non_comm = money(non_commissionable_addon_amount or 0)
    cp_customer = money(cost_plus_customer_amount or 0)
    cp_supplier = money(cost_plus_supplier_payable or 0)
    pct = money(commission_percentage or 0)

    markup_amount = max(money(0), base_amount - supplier_base)
    supplier_ratio = (supplier_base / base_amount) if base_amount > 0 and markup_amount > 0 else Decimal("1")
    group_supplier = _supplier_discount_share(money(group * supplier_ratio), group_discount_funded_by)
    promo_supplier = _supplier_discount_share(money(promo * supplier_ratio), promo_discount_funded_by)
    supplier_discount_share = money(group_supplier + promo_supplier)
    tourvaa_discount_share = money((group - group_supplier) + (promo - promo_supplier))

    commissionable_addons = max(money(0), addons - non_comm - cp_customer)
    commission_base = max(money(0), supplier_base - supplier_discount_share + commissionable_addons)
    commission_amount = money(commission_base * pct / money(100))
    supplier_gross = money(commission_base + non_comm + cp_supplier)
    supplier_net = money(supplier_gross - commission_amount)
    cost_plus_margin = money(cp_customer - cp_supplier)
    tourvaa_gross = money(commission_amount + markup_amount + cost_plus_margin - tourvaa_discount_share)
    return {
        "commission_percentage": pct,
        "commission_base_amount": commission_base,
        "commission_amount": commission_amount,
        "admin_markup_amount": markup_amount,
        "supplier_gross_amount": supplier_gross,
        "supplier_net_payable": supplier_net,
        "supplier_discount_share_amount": supplier_discount_share,
        "tourvaa_discount_share_amount": tourvaa_discount_share,
        "tourvaa_gross_revenue": tourvaa_gross,
    }


def _booking_financial_split(booking: Booking, commission_percentage) -> dict:
    """compute_booking_financial_split fed from the amounts stored on the
    booking row itself."""
    addon_total = money(booking.optional_activity_amount or 0) + money(booking.accommodation_amount or 0) + money(booking.extension_amount or 0)
    return compute_booking_financial_split(
        base_amount=booking.base_amount,
        group_discount_amount=booking.group_discount_amount,
        group_discount_funded_by=booking.group_discount_funded_by,
        promo_discount_amount=booking.discount_amount,
        promo_discount_funded_by=booking.promo_discount_funded_by,
        addon_total=addon_total,
        non_commissionable_addon_amount=booking.non_commissionable_addon_amount,
        cost_plus_customer_amount=booking.cost_plus_customer_amount,
        cost_plus_supplier_payable=booking.cost_plus_supplier_payable,
        commission_percentage=commission_percentage,
        supplier_base_amount=booking.supplier_base_amount,
    )


def _recompute_tourvaa_net_revenue(booking: Booking) -> None:
    """tourvaa_net_revenue = gross revenue - agent - affiliate, always from
    the components so recording one channel's commission can never
    overwrite the other's deduction."""
    if booking.tourvaa_gross_revenue is not None:
        gross = money(booking.tourvaa_gross_revenue)
    elif booking.tourvaa_commission_amount is not None:
        gross = money(booking.tourvaa_commission_amount)
    else:
        return
    booking.tourvaa_net_revenue = money(gross - money(booking.agent_commission_amount or 0) - money(booking.affiliate_commission_amount or 0))


def remaining_channel_commission_pool(booking: Booking):
    """How much of Tourvaa's commission is still available for a channel
    partner after the commission already paid to the other channel. None
    when the booking has no snapshot."""
    if booking.tourvaa_commission_amount is None:
        return None
    return max(money(0), money(booking.tourvaa_commission_amount) - money(booking.agent_commission_amount or 0) - money(booking.affiliate_commission_amount or 0))


def _apply_commission_snapshot(db: Session, booking: Booking, pricing_details: dict | None = None) -> None:
    """Establish the booking's financial snapshot from the amounts resolved
    at pricing time and lock it (financials_locked_at). Called at creation
    and when an admin re-prices a still-unpaid booking; everything
    downstream (supplier acceptance/ledger, admin breakdown, affiliate
    conversion, dashboards) reads these columns instead of re-deriving.

    The commission percentage is resolved once, here (slab > tour > supplier
    > platform minimum as of booking time). Agent commission is carved out
    of Tourvaa's commission and computed on the same commission base --
    never on tax, fees or agent markup -- and a rate or amount above
    Tourvaa's commission is rejected rather than letting Tourvaa's net go
    negative."""
    if pricing_details:
        for field in ("price_source", "date_price_id", "admin_markup_percentage", "supplier_base_amount", "adult_unit_price", "child_unit_price", "infant_unit_price", "single_supplement_amount", "group_discount_base_amount", "group_discount_percentage"):
            if field in pricing_details:
                setattr(booking, field, pricing_details[field])

    slab = db.query(TourPricing).filter(TourPricing.id == booking.pricing_slab_id).first() if booking.pricing_slab_id else None
    tour = db.query(Tour).filter(Tour.id == booking.tour_id).first() if booking.tour_id else None
    supplier = db.query(Supplier).filter(Supplier.id == booking.supplier_id).first() if booking.supplier_id else None
    commission_percentage = resolve_effective_commission_percentage(db, tour=tour, supplier=supplier, slab=slab)

    split = _booking_financial_split(booking, commission_percentage)
    booking.tourvaa_commission_percentage = split["commission_percentage"]
    booking.tourvaa_commission_amount = split["commission_amount"]
    booking.admin_markup_amount = split["admin_markup_amount"]
    booking.commission_base_amount = split["commission_base_amount"]
    booking.supplier_gross_amount = split["supplier_gross_amount"]
    booking.supplier_net_payable = split["supplier_net_payable"]
    booking.supplier_discount_share_amount = split["supplier_discount_share_amount"]
    booking.tourvaa_discount_share_amount = split["tourvaa_discount_share_amount"]
    booking.tourvaa_gross_revenue = split["tourvaa_gross_revenue"]
    booking.agent_commission_base_amount = None
    booking.agent_commission_percentage = None
    booking.agent_commission_amount = None

    if booking.booking_source == "agent" and booking.agent:
        agent = booking.agent
        discount_type = (agent.discount_type or "").strip().lower()
        discount_value = money(agent.discount_value or 0)
        commission_pct = split["commission_percentage"]
        if discount_type == "percentage" and commission_pct > 0 and discount_value > commission_pct:
            raise HTTPException(
                status_code=422,
                detail=f"This agent's commission rate ({discount_value}%) cannot exceed Tourvaa's commission on this tour ({commission_pct}%).",
            )
        agent_base = split["commission_base_amount"]
        agent_commission_amount = compute_agent_commission(agent, agent_base)
        if agent_commission_amount > split["commission_amount"]:
            raise HTTPException(
                status_code=422,
                detail="This agent's commission amount cannot exceed Tourvaa's commission on this booking.",
            )
        booking.agent_commission_base_amount = agent_base
        booking.agent_commission_percentage = discount_value if discount_type == "percentage" else None
        booking.agent_commission_amount = agent_commission_amount

    _recompute_tourvaa_net_revenue(booking)
    booking.financials_locked_at = utcnow()


def _lock_legacy_booking_financials(db: Session, booking: Booking) -> None:
    """Bookings created before the snapshot existed are locked from their
    own stored amounts the first time they need a payout figure (supplier
    acceptance). The commission percentage is the one stored at creation
    when present, otherwise resolved once, now."""
    if booking.financials_locked_at is not None:
        return
    if booking.tourvaa_commission_percentage is not None:
        pct = money(booking.tourvaa_commission_percentage)
    else:
        slab = db.query(TourPricing).filter(TourPricing.id == booking.pricing_slab_id).first() if booking.pricing_slab_id else None
        tour = db.query(Tour).filter(Tour.id == booking.tour_id).first() if booking.tour_id else None
        supplier = db.query(Supplier).filter(Supplier.id == booking.supplier_id).first() if booking.supplier_id else None
        pct = resolve_effective_commission_percentage(db, tour=tour, supplier=supplier, slab=slab)
    split = _booking_financial_split(booking, pct)
    booking.tourvaa_commission_percentage = split["commission_percentage"]
    booking.tourvaa_commission_amount = split["commission_amount"]
    booking.commission_base_amount = split["commission_base_amount"]
    booking.supplier_gross_amount = split["supplier_gross_amount"]
    booking.supplier_net_payable = split["supplier_net_payable"]
    booking.supplier_discount_share_amount = split["supplier_discount_share_amount"]
    booking.tourvaa_discount_share_amount = split["tourvaa_discount_share_amount"]
    booking.tourvaa_gross_revenue = split["tourvaa_gross_revenue"]
    _recompute_tourvaa_net_revenue(booking)
    booking.financials_locked_at = utcnow()


def compute_agent_commission(agent, gross_amount):
    """Platform-paid commission Tourvaa owes an agent -- the agent's ONLY
    earning under the commission-only model. gross_amount must be the
    booking's commission base (tour selling amount), never the customer
    total with tax, fees or agent markup. Single shared formula used by the
    booking snapshot and the dashboard's legacy fallback."""
    discount_type = ((agent.discount_type if agent else None) or "").strip().lower()
    discount_value = money(agent.discount_value or 0) if agent else money(0)
    gross_amount = money(gross_amount or 0)
    if discount_type == "percentage":
        return money((gross_amount * discount_value) / 100)
    if discount_type == "fixed":
        return discount_value
    return money(0)


def _settle_cancelled_booking_payments(
    db: Session,
    booking: Booking,
    actor: User | None,
    request: Request | None,
    reason: str,
) -> None:
    from app.models.payments import Payment
    from app.schemas.payments import PaymentVoid, RefundRequest
    from app.services.payments import process_refund, void_payment

    original_status = (booking.payment_status or "").lower()
    payments = list(db.query(Payment).filter(Payment.booking_id == booking.id).all())
    found_refundable_payment = False
    for payment in payments:
        captured = money(payment.captured_amount or payment.paid_amount)
        refunded = money(payment.refunded_amount)
        if captured > refunded:
            found_refundable_payment = True
            booking.payment_status = "refund_pending"
            process_refund(
                db,
                payment.id,
                RefundRequest(amount=captured - refunded, reason=reason),
                actor=actor,
                request=request,
            )
        elif payment.payment_status in {"authorized", "pending"}:
            void_payment(
                db,
                payment.id,
                PaymentVoid(reason=reason),
                actor=actor,
                request=request,
            )

    if found_refundable_payment:
        booking.payment_status = "refunded"
    elif original_status == "refund_pending":
        booking.payment_status = "refund_pending"
    elif money(booking.amount_paid) <= 0:
        booking.payment_status = "voided"
    booking.amount_pending = money(0)


def _money_total(rows) -> str:
    return money_str(sum(money(getattr(row, "total_price", 0)) for row in rows))


def serialize_status_history(row: BookingStatusHistory) -> dict:
    return {
        "id": row.id,
        "booking_id": row.booking_id,
        "old_status": row.old_status,
        "new_status": row.new_status,
        "changed_by_user_id": row.changed_by_user_id,
        "change_source": row.change_source,
        "reason": row.reason,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
    }


def _resolve_agent_invoice_email(db: Session, agent_id: int | None) -> str | None:
    """Best email to send an agent's own invoices to: their dedicated
    billing contact (AgentInvoicing.email) first, falling back to their
    login email, then their primary AgentContact - mirrors the fallback
    order already used to reach a supplier's billing contact elsewhere."""
    if not agent_id:
        return None
    from app.models.agents import Agent, AgentInvoicing
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return None
    invoicing = db.query(AgentInvoicing).filter(AgentInvoicing.agent_id == agent_id).first()
    if invoicing and invoicing.email:
        return invoicing.email
    if agent.user and agent.user.email:
        return agent.user.email
    primary_contact = next((c for c in agent.contacts if c.is_primary and c.email), None) or next((c for c in agent.contacts if c.email), None)
    return primary_contact.email if primary_contact else None


def _balance_due_date(db: Session, booking: Booking):
    """When a balance is outstanding on a deposit / Reserve Now booking, the
    date it is due. None if the booking is fully paid, or has no tour or
    departure date to count back from.

    Client rule, the same for agents (Reserve Now) and customers (Secure
    with a Deposit): the start of the Xth week before the tour's Minimum
    Advance Booking cutoff -- the exact date checkout showed when the
    booking was made (see tour_availability.deposit_balance_due_date).
    Computed without regard to today's date, so it keeps returning the due
    date after it has passed and notify_overdue_agent_balances can flag it."""
    if money(booking.amount_pending or 0) <= 0:
        return None
    if booking.tour_id is None or booking.tour_start_date is None:
        return None
    is_agent_reserve = booking.booking_source == "agent" and (
        booking.agent_payment_method == "pay_later"
        or (booking.agent_payment_method == "credit" and money(booking.amount_paid or 0) <= 0)
    )
    # A customer booking with nothing paid yet has no deposit, so no balance
    # schedule either -- it's simply unpaid.
    if not is_agent_reserve and money(booking.amount_paid or 0) <= 0:
        return None
    from app.services.tour_availability import deposit_balance_due_date
    return deposit_balance_due_date(db, booking.tour_id, booking.tour_start_date)[0]


def _deposit_config(db: Session, booking: Booking) -> Optional[dict]:
    """Effective deposit terms for this booking's tour, with the tour's own
    settings falling back to the admin-configured platform defaults
    (default_deposit_percentage/default_deposit_cutoff_days) wherever the
    tour hasn't set its own - mirroring
    payments_gateway._minimum_deposit_amount, which resolves the same
    fallback server-side when actually validating a payment. The cutoff is
    already resolved against tour_start_date here too, so a client (e.g.
    the customer portal's pay-balance modal) never has to reimplement the
    days-to-departure math itself."""
    tour = getattr(booking, "tour", None)
    deposit_type = (getattr(tour, "deposit_type", "fixed") if tour else "fixed") or "fixed"
    percentage = getattr(tour, "deposit_percentage", None) if tour else None
    fixed = getattr(tour, "booking_deposit", None) if tour else None
    if deposit_type != "percentage" and not fixed:
        # Tour has no deposit of its own configured (or no tour at all) --
        # fall back to the platform default percentage rather than treating
        # "fixed" (the column default) as "no deposit offered".
        deposit_type = "percentage"
        percentage = float(get_default_deposit_percentage(db))
    elif deposit_type == "percentage" and not percentage:
        percentage = float(get_default_deposit_percentage(db))

    cutoff_days = getattr(tour, "deposit_cutoff_days", None) if tour else None
    if cutoff_days is None:
        cutoff_days = get_default_deposit_cutoff_days(db)
    still_available = True
    if cutoff_days is not None and booking.tour_start_date is not None:
        days_to_departure = (as_aware_utc(booking.tour_start_date) - utcnow()).days
        still_available = days_to_departure >= cutoff_days
    return {
        "deposit_type": deposit_type,
        "deposit_percentage": float(percentage) if percentage is not None else None,
        "booking_deposit": money_str(fixed) if fixed else None,
        "deposit_cutoff_days": cutoff_days,
        "balance_payment_deadline_days": getattr(tour, "balance_payment_deadline_days", None) if tour else None,
        "still_available": still_available,
    }


def serialize_booking(db: Session, booking: Booking, detail: bool = False, include_supplier_breakdown: bool = False, hide_supplier_identity: bool = False) -> dict:
    data = {
        "id": booking.id,
        "booking_code": booking.booking_code or _booking_code(db, booking.id, booking.booking_source),
        "customer_id": booking.customer_id,
        "customer_name": booking.customer.full_name if booking.customer else None,
        "customer_email": booking.customer.email if booking.customer else None,
        "tour_id": booking.tour_id,
        "tour_slug": booking.tour.slug if booking.tour else None,
        "tour_image": booking.tour.banner_image if booking.tour else None,
        "tour_country_name": booking.tour.country.country_name if booking.tour and booking.tour.country else booking.country,
        "tour_calendar_id": booking.tour_calendar_id,
        # Kept even when hide_supplier_identity is set: it's never rendered
        # in the customer/agent UI, only used as a "does this booking have a
        # supplier assigned yet" signal (e.g. gating the support message
        # thread) - supplier_name/the supplier dict below are the fields
        # that actually identify who's fulfilling the tour.
        "supplier_id": booking.supplier_id,
        "agent_id": booking.agent_id,
        "affiliate_id": booking.affiliate_id,
        "booking_source": booking.booking_source,
        "country_id": booking.country_id,
        "city_id": booking.city_id,
        "tour_name": booking.tour_name,
        "tour_date": booking.tour_date,
        "tour_start_date": booking.tour_start_date,
        "tour_end_date": booking.tour_end_date,
        "country": booking.country,
        # Suppliers are a B2B/back-office relationship - customers and agents
        # should never see who is actually fulfilling their tour, only
        # Tourvaa (see get_booking_detail/get_bookings' hide_supplier_identity
        # gate below, mirroring the existing include_supplier_breakdown
        # admin-only pattern).
        "supplier_name": None if hide_supplier_identity else booking.supplier_name,
        "no_of_adults": booking.no_of_adults,
        "no_of_children": booking.no_of_children,
        "no_of_infants": booking.no_of_infants,
        "no_of_rooms": booking.no_of_rooms,
        "adults_count": booking.adults_count,
        "children_count": booking.children_count,
        "total_travellers": booking.total_travellers,
        "currency": booking.currency,
        "total_cost": money_str(booking.total_cost),
        "base_amount": money_str(booking.base_amount),
        "optional_activity_amount": money_str(booking.optional_activity_amount),
        "accommodation_amount": money_str(booking.accommodation_amount),
        "extension_amount": money_str(booking.extension_amount),
        "group_discount_amount": money_str(booking.group_discount_amount),
        "group_discount_funded_by": booking.group_discount_funded_by,
        "discount_amount": money_str(booking.discount_amount),
        "promo_discount_funded_by": booking.promo_discount_funded_by,
        "tax_amount": money_str(booking.tax_amount),
        "surcharge_amount": money_str(booking.surcharge_amount),
        "service_fee_amount": money_str(booking.service_fee_amount) if booking.service_fee_amount is not None else None,
        "gateway_fee_amount": money_str(booking.gateway_fee_amount) if booking.gateway_fee_amount is not None else None,
        "final_amount": money_str(booking.final_amount),
        "agent_net_price": money_str(booking.agent_net_price),
        "agent_markup": money_str(booking.agent_markup),
        "customer_selling_price": money_str(booking.customer_selling_price),
        "amount_paid": money_str(booking.amount_paid),
        "amount_pending": money_str(booking.amount_pending),
        "balance_due_date": _balance_due_date(db, booking),
        "payment_due_date": booking.payment_due_date,
        "booking_status": booking.booking_status,
        "supplier_acceptance_status": booking.supplier_acceptance_status,
        "payment_status": booking.payment_status,
        "payment_type": booking.payment_type,
        "agent_payment_method": booking.agent_payment_method,
        "agent_reference": booking.agent_reference,
        "promo_code": booking.promo_code,
        "notes": booking.notes,
        "customer_notes": booking.customer_notes,
        "admin_notes": booking.admin_notes,
        "cancellation_reason": booking.cancellation_reason,
        "cancellation_source": booking.cancellation_source,
        "cancelled_at": booking.cancelled_at,
        "created_at": booking.created_at,
        "updated_at": booking.updated_at,
    }
    if detail:
        data.update({
            "pricing_snapshot": {
                "pricing_slab_id": booking.pricing_slab_id,
                "supplier_price": money_str(booking.supplier_price) if booking.supplier_price is not None else None,
                "supplier_currency": booking.supplier_currency,
                "tourvaa_selling_price": money_str(booking.tourvaa_selling_price) if booking.tourvaa_selling_price is not None else None,
                "display_currency": booking.display_currency,
                "exchange_rate": str(booking.exchange_rate) if booking.exchange_rate is not None else None,
                "exchange_rate_source": booking.exchange_rate_source,
                "exchange_rate_captured_at": booking.exchange_rate_captured_at,
                "converted_customer_amount": money_str(booking.converted_customer_amount) if booking.converted_customer_amount is not None else None,
            },
            "customer": {"id": booking.customer.id, "name": booking.customer.full_name, "email": booking.customer.email} if booking.customer else None,
            "supplier": None if hide_supplier_identity else ({"id": booking.supplier.id, "supplier_name": booking.supplier.supplier_name} if booking.supplier else None),
            "travellers": [serialize_traveller(t) for t in booking.travellers],
            "optional_activities": [serialize_activity(a) for a in booking.optional_activities],
            "accommodations": [serialize_accommodation(a) for a in booking.accommodations],
            "extensions": [serialize_extension(e) for e in booking.extensions],
            "payments": [serialize_payment(p) for p in booking.payments],
            "status_history": [serialize_status_history(h) for h in booking.status_history],
            "communications": [serialize_communication(c) for c in booking.communications],
            "price_breakdown": {
                "base_amount": money_str(booking.base_amount),
                "optional_activity_amount": _money_total(booking.optional_activities),
                "accommodation_amount": _money_total(booking.accommodations),
                "extension_amount": _money_total(booking.extensions),
                "group_discount_amount": money_str(booking.group_discount_amount),
                "group_discount_funded_by": booking.group_discount_funded_by,
                "discount_amount": money_str(booking.discount_amount),
                "promo_discount_funded_by": booking.promo_discount_funded_by,
                "tax_amount": money_str(booking.tax_amount),
                "surcharge_amount": money_str(booking.surcharge_amount),
                "service_fee_amount": money_str(booking.service_fee_amount) if booking.service_fee_amount is not None else None,
                "gateway_fee_amount": money_str(booking.gateway_fee_amount) if booking.gateway_fee_amount is not None else None,
                "final_amount": money_str(booking.final_amount),
                "agent_net_price": money_str(booking.agent_net_price),
                "agent_markup": money_str(booking.agent_markup),
                "customer_selling_price": money_str(booking.customer_selling_price),
            },
            "payment_summary": {"status": booking.payment_status, "paid": money_str(booking.amount_paid), "pending": money_str(booking.amount_pending), "balance_due_date": _balance_due_date(db, booking)},
            "deposit_config": _deposit_config(db, booking),
            "invoice_summary": None,
        })
        # Admin-only: what the supplier is owed after commission, alongside
        # the customer-facing price, in the booking's own currency -- never
        # exposed to the customer/agent/supplier's own view of this same
        # serializer (see get_booking_detail's include_supplier_breakdown gate).
        if include_supplier_breakdown:
            breakdown = compute_booking_supplier_financials(db, booking)
            supplier_ledger = (
                db.query(SupplierLedger)
                .filter(SupplierLedger.booking_id == booking.id)
                .order_by(SupplierLedger.id.desc())
                .first()
            )
            supplier_payout = None
            if supplier_ledger:
                supplier_payout = (
                    db.query(SupplierPayout)
                    .join(SupplierPayoutItem, SupplierPayoutItem.payout_id == SupplierPayout.id)
                    .filter(SupplierPayoutItem.ledger_id == supplier_ledger.id)
                    .order_by(SupplierPayout.paid_at.desc(), SupplierPayout.id.desc())
                    .first()
                )
            data["supplier_breakdown"] = {
                "currency": breakdown["currency"],
                "gross_amount": money_str(breakdown["gross_amount"]),
                "commission_percentage": money_str(breakdown["commission_percentage"]),
                "commission_amount": money_str(breakdown["commission_amount"]),
                "net_payable": money_str(breakdown["net_payable"]),
                "customer_price": money_str(breakdown["customer_price"]),
                "customer_price_currency": breakdown["customer_price_currency"],
                "commission_base_amount": money_str(breakdown["commission_base_amount"]),
                # Tourvaa's own revenue on the tour: commission + cost-plus
                # margin - Tourvaa-funded discounts (before agent/affiliate
                # payouts). Tax, service fee and gateway fee are separate
                # pass-through buckets, not margin.
                "tourvaa_margin": money_str(booking.tourvaa_gross_revenue) if booking.tourvaa_gross_revenue is not None else money_str(breakdown["commission_amount"]),
                "payment_status": supplier_ledger.status if supplier_ledger else "pending",
                "payment_date": supplier_payout.paid_at if supplier_payout and supplier_payout.status == "paid" else None,
            } if breakdown else None
            # Booking financial snapshot (see Booking model /
            # _apply_commission_snapshot) - admin-only, same gate as
            # supplier_breakdown above, since these expose exactly how the
            # money split between supplier/Tourvaa/agent/affiliate.
            data.update({
                "price_source": booking.price_source,
                "date_price_id": booking.date_price_id,
                "adult_unit_price": money_str(booking.adult_unit_price) if booking.adult_unit_price is not None else None,
                "child_unit_price": money_str(booking.child_unit_price) if booking.child_unit_price is not None else None,
                "infant_unit_price": money_str(booking.infant_unit_price) if booking.infant_unit_price is not None else None,
                "group_discount_base_amount": money_str(booking.group_discount_base_amount) if booking.group_discount_base_amount is not None else None,
                "group_discount_percentage": str(booking.group_discount_percentage) if booking.group_discount_percentage is not None else None,
                "admin_markup_percentage": money_str(booking.admin_markup_percentage) if booking.admin_markup_percentage is not None else None,
                "supplier_base_amount": money_str(booking.supplier_base_amount) if booking.supplier_base_amount is not None else None,
                "admin_markup_amount": money_str(booking.admin_markup_amount) if booking.admin_markup_amount is not None else None,
                "commission_base_amount": money_str(booking.commission_base_amount) if booking.commission_base_amount is not None else None,
                "supplier_gross_amount": money_str(booking.supplier_gross_amount) if booking.supplier_gross_amount is not None else None,
                "supplier_discount_share_amount": money_str(booking.supplier_discount_share_amount) if booking.supplier_discount_share_amount is not None else None,
                "tourvaa_discount_share_amount": money_str(booking.tourvaa_discount_share_amount) if booking.tourvaa_discount_share_amount is not None else None,
                "tourvaa_gross_revenue": money_str(booking.tourvaa_gross_revenue) if booking.tourvaa_gross_revenue is not None else None,
                "agent_commission_base_amount": money_str(booking.agent_commission_base_amount) if booking.agent_commission_base_amount is not None else None,
                "affiliate_commission_base_amount": money_str(booking.affiliate_commission_base_amount) if booking.affiliate_commission_base_amount is not None else None,
                "financials_locked_at": booking.financials_locked_at,
            })
            data.update({
                "tourvaa_commission_percentage": money_str(booking.tourvaa_commission_percentage) if booking.tourvaa_commission_percentage is not None else None,
                "tourvaa_commission_amount": money_str(booking.tourvaa_commission_amount) if booking.tourvaa_commission_amount is not None else None,
                "supplier_net_payable": money_str(booking.supplier_net_payable) if booking.supplier_net_payable is not None else None,
                "agent_commission_percentage": money_str(booking.agent_commission_percentage) if booking.agent_commission_percentage is not None else None,
                "agent_commission_amount": money_str(booking.agent_commission_amount) if booking.agent_commission_amount is not None else None,
                "affiliate_commission_percentage": money_str(booking.affiliate_commission_percentage) if booking.affiliate_commission_percentage is not None else None,
                "affiliate_commission_amount": money_str(booking.affiliate_commission_amount) if booking.affiliate_commission_amount is not None else None,
                "tourvaa_net_revenue": money_str(booking.tourvaa_net_revenue) if booking.tourvaa_net_revenue is not None else None,
                "non_commissionable_addon_amount": money_str(booking.non_commissionable_addon_amount) if booking.non_commissionable_addon_amount is not None else None,
                "cost_plus_supplier_payable": money_str(booking.cost_plus_supplier_payable) if booking.cost_plus_supplier_payable is not None else None,
            })
    return data


_SUPPLIER_HIDDEN_MONEY_FIELDS = ("amount_paid", "amount_pending", "agent_markup", "tax_amount", "surcharge_amount", "service_fee_amount", "gateway_fee_amount")


def supplier_booking_value(booking: Booking):
    """What a booking is worth at the supplier's own prices (the locked
    snapshot's supplier gross) -- the amount any supplier-facing screen,
    report or email may show. Never the customer total, which includes
    Tourvaa's admin markup, tax and fees. Bookings without a snapshot
    carried no markup, so their final amount is used."""
    if booking.supplier_gross_amount is not None:
        return booking.supplier_gross_amount
    if booking.supplier_net_payable is not None:
        return money(booking.supplier_net_payable) + money(booking.tourvaa_commission_amount or 0)
    return booking.final_amount


def _is_booking_fully_paid(booking: Booking) -> bool:
    """Whether a supplier may be asked to action the booking.

    The booking payment status is the primary workflow state, but checking the
    captured amount too prevents a stale ``paid`` flag from exposing a
    supplier assignment before checkout has actually settled.
    """
    if booking.payment_status != "paid":
        return False
    total = money(booking.final_amount or booking.total_cost or 0)
    return total <= 0 or money(booking.amount_paid or 0) >= total


def _supplier_safe(data: dict, booking: Booking) -> dict:
    """A supplier's own view of a booking never shows the customer-side
    money (which includes Tourvaa's admin markup, tax and fees): the headline
    amounts are replaced by the supplier-price equivalents from the locked
    snapshot (supplier_base_amount / supplier_gross_amount), and payment
    amounts are dropped. Bookings without a snapshot fall back to the stored
    amounts, which carried no markup."""
    supplier_total = supplier_booking_value(booking)
    if supplier_total is not None:
        for key in ("final_amount", "total_cost", "customer_selling_price", "agent_net_price"):
            data[key] = money_str(supplier_total)
    if booking.supplier_base_amount is not None:
        data["base_amount"] = money_str(booking.supplier_base_amount)
    for key in _SUPPLIER_HIDDEN_MONEY_FIELDS:
        data[key] = None
    if isinstance(data.get("price_breakdown"), dict):
        pb = data["price_breakdown"]
        for key in ("final_amount", "customer_selling_price", "agent_net_price"):
            if key in pb and supplier_total is not None:
                pb[key] = money_str(supplier_total)
        if booking.supplier_base_amount is not None:
            pb["base_amount"] = money_str(booking.supplier_base_amount)
        for key in _SUPPLIER_HIDDEN_MONEY_FIELDS:
            if key in pb:
                pb[key] = None
    if isinstance(data.get("pricing_snapshot"), dict):
        data["pricing_snapshot"]["tourvaa_selling_price"] = None
        data["pricing_snapshot"]["converted_customer_amount"] = None
    if isinstance(data.get("payment_summary"), dict):
        data["payment_summary"]["paid"] = None
        data["payment_summary"]["pending"] = None
    if "payments" in data:
        data["payments"] = []
    return data


def serialize_booking_for_actor(db: Session, booking: Booking, actor: Optional[User], detail: bool = True) -> dict:
    """serialize_booking with the per-role gates every actor-facing return
    applies: supplier identity hidden from customers/agents, and customer-
    side money (with Tourvaa's markup) hidden from suppliers."""
    role = _user_role(actor)
    data = serialize_booking(db, booking, detail=detail, hide_supplier_identity=role in ("customer", "agent"))
    if role == "supplier":
        return _supplier_safe(data, booking)
    return _hide_supplier_reassignment_from_external_partner(data, booking, role)


def _hide_supplier_reassignment_from_external_partner(data: dict, booking: Booking, role: str) -> dict:
    """Keep a supplier withdrawal operationally internal to Tourvaa.

    A supplier withdrawal initiates reassignment rather than cancelling the
    traveller's booking. Customers and agents retain the last confirmed view
    while Operations assigns another supplier.
    """
    if role not in {"customer", "agent"}:
        return data
    if booking.booking_status != "supplier_reassignment_required" or booking.cancellation_source != "supplier_reassignment":
        return data
    data["booking_status"] = "confirmed"
    data["supplier_acceptance_status"] = "accepted"
    data["cancellation_reason"] = None
    data["cancellation_source"] = None
    data["cancelled_at"] = None
    if isinstance(data.get("status_history"), list):
        data["status_history"] = [
            row for row in data["status_history"]
            if row.get("change_source") != "supplier_reassignment"
        ]
    return data


def _agent_payment_summary(db: Session, booking: Booking) -> dict | None:
    """Return agent-only settlement data from the authoritative ledger records."""
    if booking.booking_source != "agent" or booking.agent_id is None:
        return None

    from app.models.agent_ledger import AgentLedger, AgentPayout, AgentPayoutItem
    from app.models.invoices import Invoice

    ledger = db.query(AgentLedger).filter(AgentLedger.booking_id == booking.id).order_by(AgentLedger.id.desc()).first()
    payout = None
    if ledger:
        payout = (
            db.query(AgentPayout)
            .join(AgentPayoutItem, AgentPayoutItem.payout_id == AgentPayout.id)
            .filter(AgentPayoutItem.ledger_id == ledger.id, AgentPayout.status == "paid")
            .order_by(AgentPayout.paid_at.desc(), AgentPayout.id.desc())
            .first()
        )
    invoice = db.query(Invoice).filter(Invoice.booking_id == booking.id).order_by(Invoice.id.desc()).first()
    reserved = (booking.agent_payment_method or "").lower() in {"pay_later", "credit", "bank_transfer"}
    total_booking_amount = money(booking.final_amount)
    commission_amount = money(ledger.commission_amount if ledger else booking.agent_commission_amount)
    # The amount an agent owes Tourvaa is the booking total less the
    # commission that Tourvaa pays the agent.  Do not reuse agent_net_price:
    # it is a legacy price snapshot and is not this settlement amount.
    agent_price_after_commission = max(money(0), total_booking_amount - commission_amount)

    return {
        "transaction_type": "Booking Reserved" if reserved else "Full Payment",
        "is_reserved": reserved,
        "amount_paid": money_str(booking.amount_paid),
        "total_booking_amount": money_str(total_booking_amount),
        # Booking snapshot is the approved agent rate. Ledger rows created
        # before this was persisted calculated a misleading effective rate
        # against the customer total, so never use that value for display.
        "commission_percentage": money_str(booking.agent_commission_percentage if booking.agent_commission_percentage is not None else ledger.commission_percentage if ledger else None),
        "commission_amount": money_str(commission_amount),
        "commission_payable": money_str(ledger.net_payable if ledger else booking.agent_commission_amount),
        "commission_status": ledger.status if ledger else "pending",
        "commission_payment_date": payout.paid_at.isoformat() if payout and payout.paid_at else None,
        "agent_price_after_commission": money_str(agent_price_after_commission),
        "invoice_status": invoice.status if invoice else "pending",
        "payment_due_date": (
            invoice.balance_due_date.isoformat() if invoice and invoice.balance_due_date
            else booking.payment_due_date.isoformat() if booking.payment_due_date else None
        ),
    }


def _supplier_payment_summary(db: Session, booking: Booking) -> dict | None:
    """Supplier-safe settlement fields; never includes the customer price."""
    breakdown = compute_booking_supplier_financials(db, booking)
    if not breakdown:
        return None
    ledger = db.query(SupplierLedger).filter(SupplierLedger.booking_id == booking.id).order_by(SupplierLedger.id.desc()).first()
    payout = None
    if ledger:
        payout = (
            db.query(SupplierPayout)
            .join(SupplierPayoutItem, SupplierPayoutItem.payout_id == SupplierPayout.id)
            .filter(SupplierPayoutItem.ledger_id == ledger.id, SupplierPayout.status == "paid")
            .order_by(SupplierPayout.paid_at.desc(), SupplierPayout.id.desc())
            .first()
        )
    return {
        "currency": breakdown["currency"],
        "gross_amount": money_str(breakdown["gross_amount"]),
        "commission_percentage": money_str(breakdown["commission_percentage"]),
        "commission_amount": money_str(breakdown["commission_amount"]),
        "net_payable": money_str(breakdown["net_payable"]),
        "payment_status": ledger.status if ledger else "pending",
        "payment_date": payout.paid_at.isoformat() if payout and payout.paid_at else None,
    }


def serialize_traveller(t: BookingTraveller) -> dict:
    return {"id": t.id, "traveller_type": t.traveller_type, "first_name": t.first_name, "last_name": t.last_name, "full_name": t.full_name, "age": t.age, "gender": t.gender, "nationality": t.nationality, "passport_number": _mask_passport(t.passport_number), "email": t.email, "phone": t.phone, "is_primary_contact": bool(t.is_primary_contact), "special_requirements": t.special_requirements, "pickup_location": t.pickup_location, "emergency_contact": t.emergency_contact}


def serialize_activity(a: BookingOptionalActivity) -> dict:
    return {"id": a.id, "tour_optional_activity_id": a.tour_optional_activity_id, "activity_name_snapshot": a.activity_name_snapshot, "quantity": a.quantity, "unit_price": money_str(a.unit_price), "total_price": money_str(a.total_price)}


def serialize_accommodation(a: BookingAccommodation) -> dict:
    return {"id": a.id, "tour_accommodation_extra_id": a.tour_accommodation_extra_id, "accommodation_name_snapshot": a.accommodation_name_snapshot, "quantity": a.quantity, "price_type": a.price_type, "unit_price": money_str(a.unit_price), "total_price": money_str(a.total_price)}


def serialize_extension(e: BookingExtension) -> dict:
    return {"id": e.id, "tour_extension_id": e.tour_extension_id, "extension_tour_id": e.extension_tour_id, "extension_name_snapshot": e.extension_name_snapshot, "quantity": e.quantity, "unit_price": money_str(e.unit_price), "total_price": money_str(e.total_price)}


def serialize_communication(c: BookingCommunication) -> dict:
    return {
        "id": c.id,
        "booking_id": c.booking_id,
        "sender_user_id": c.sender_user_id,
        "sender_type": c.sender_type,
        "message_type": c.message_type,
        "subject": c.subject,
        "message": c.message,
        "visibility": c.visibility,
        "created_at": c.created_at,
        "replies": [
            {
                "id": r.id,
                "communication_id": r.communication_id,
                "sender_user_id": r.sender_user_id,
                "sender_type": r.sender_type,
                "message": r.message,
                "created_at": r.created_at,
            }
            for r in c.replies
        ],
    }


def get_booking_by_id(db: Session, booking_id: int, for_update: bool = False) -> Booking:
    query = db.query(Booking).filter(Booking.id == booking_id)
    if for_update:
        query = query.with_for_update()
    booking = query.first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _start_supplier_decision(booking: Booking, decision: str) -> bool:
    """Validate a supplier decision and return False when it is an idempotent retry."""
    if not booking.supplier_id:
        raise HTTPException(status_code=400, detail="No supplier is assigned to this booking")
    current = booking.supplier_acceptance_status
    if current == decision:
        return False
    if current != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Supplier decision is already {current}; it cannot be changed to {decision}",
        )
    return True


def _validate_supplier_lifecycle_transition(booking: Booking, target_status: str) -> bool:
    """Validate supplier-owned tour execution transitions and make retries idempotent."""
    current = (booking.booking_status or "").lower()
    if current == target_status:
        return False
    if booking.supplier_acceptance_status != "accepted":
        raise HTTPException(status_code=409, detail="The supplier must accept the booking before updating tour execution")
    allowed_sources = {
        "ongoing": {"confirmed", "postponed"},
        # Keep confirmed -> completed for backward compatibility with existing clients.
        "completed": {"confirmed", "ongoing"},
    }
    if target_status not in allowed_sources or current not in allowed_sources[target_status]:
        allowed = " or ".join(sorted(allowed_sources.get(target_status, set())))
        raise HTTPException(status_code=400, detail=f"Only {allowed} bookings can be marked as {target_status}")
    return True


def _resolve_discount(db: Session, promo_code: str | None, tour, subtotal, consume: bool = False, travel_date=None):
    """Look up and validate a promo code against tour_discounts. Raises 400 if the
    code doesn't exist or doesn't apply. When no code is supplied, auto-applies
    the same best-active discount the storefront/booking-flow already
    highlighted for this tour (services.discounts.find_best_discount_row) --
    so the discounted price a customer/agent sees is always what they're
    actually charged, with no separate promo code required.

    Returns (amount, funded_by) where funded_by is the resolved TourDiscount
    row's funded_by ("SUPPLIER"/"TOURVAA"/"SHARED"), or None when no discount
    applied at all. Snapshotted onto the booking (Booking.promo_discount_funded_by)
    and read by compute_booking_supplier_financials, which decides whether the
    supplier's payout absorbs this discount (SUPPLIER, the default -- and the
    amount is already baked into gross_amount via booking.final_amount by the
    time that function runs), is paid as if it never happened (TOURVAA), or
    splits it 50/50 (SHARED)."""
    if not promo_code or not promo_code.strip():
        if not tour:
            return money(0), None
        from app.services.discounts import find_active_discount_stack, discount_amount_for
        # Supplier discounts have already reduced the supplier units before
        # markup in _price_booking. Only Tourvaa's own discount belongs here,
        # after markup, against the publishable/storefront subtotal.
        row = find_active_discount_stack(db, tour, lock=consume, effective_at=travel_date)["tourvaa"]
        if not row or money(subtotal) < money(row.minimum_booking_amount or 0):
            return money(0), None
        if row.usage_limit is not None and (row.used_count or 0) >= row.usage_limit:
            return money(0), None
        amount = min(money(discount_amount_for(row, float(subtotal))), money(subtotal))
        if amount <= 0:
            return money(0), None
        if consume:
            row.used_count = (row.used_count or 0) + 1
        return money(amount), "TOURVAA"
    code = promo_code.strip().upper()
    discount_query = db.query(TourDiscount).filter(func.upper(TourDiscount.discount_code) == code, TourDiscount.status == "active")
    if consume:
        # Row-locked so two concurrent bookings against the same promo code
        # can't both pass the usage_limit check below and both increment
        # used_count past it.
        discount_query = discount_query.with_for_update()
    discount = discount_query.first()
    if not discount:
        raise HTTPException(status_code=400, detail="Invalid or inactive promo code")
    # MySQL returns these DateTime columns naive (stored as UTC) -- normalize
    # before comparing against the aware utcnow(), or this raises TypeError
    # (a 500 at checkout for every dated promo code). End dates are picked as
    # a calendar day in the admin, so a code "valid till 31 Dec" works all
    # of 31 Dec -- same rule as discounts.find_best_discount_row.
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if discount.start_date and now < as_aware_utc(discount.start_date):
        raise HTTPException(status_code=400, detail="Promo code is not yet active")
    if discount.end_date and as_aware_utc(discount.end_date) < today_start:
        raise HTTPException(status_code=400, detail="Promo code has expired")
    if discount.usage_limit is not None and (discount.used_count or 0) >= discount.usage_limit:
        raise HTTPException(status_code=400, detail="Promo code usage limit has been reached")
    if money(subtotal) < money(discount.minimum_booking_amount or 0):
        raise HTTPException(status_code=400, detail=f"Promo code requires a minimum booking amount of {discount.minimum_booking_amount}")
    if discount.discount_scope == "tour" and (not tour or discount.tour_id != tour.id):
        raise HTTPException(status_code=400, detail="Promo code is not valid for this tour")
    if discount.discount_scope == "category" and (not tour or discount.category_id != tour.category_id):
        raise HTTPException(status_code=400, detail="Promo code is not valid for this tour category")
    if discount.discount_scope == "country" and (not tour or discount.country_id != tour.country_id):
        raise HTTPException(status_code=400, detail="Promo code is not valid for this country")
    if discount.discount_type == "percentage":
        amount = money(subtotal) * money(discount.discount_value) / money(100)
    else:
        amount = money(discount.discount_value)
    amount = min(money(amount), money(subtotal))
    if consume:
        discount.used_count = (discount.used_count or 0) + 1
    return money(amount), (discount.funded_by or "SUPPLIER")


def resolve_effective_commission_percentage(db: Session, *, tour=None, supplier=None, slab=None):
    """Single source of truth for which commission percentage applies:
    the specific TourPricing slab's own rate (set in
    services.tours._apply_pricing_computation, itself already floor-
    enforced against this same hierarchy) wins outright, then an admin
    per-tour override (Tour.commission_percentage), then the supplier's own
    rate, then the platform minimum. Used by both supplier_accept_booking
    (the real ledger) and the supplier-facing commission calculator, so
    they can never disagree."""
    from app.services.settings import get_commission_percentage

    if slab is not None and getattr(slab, "commission_percentage", None) is not None:
        return money(slab.commission_percentage)
    if tour is not None and tour.commission_percentage is not None:
        return money(tour.commission_percentage)
    if supplier is not None and supplier.commission_percentage is not None:
        return money(supplier.commission_percentage)
    return get_commission_percentage(db)


def _resolve_group_discount(db: Session, tour_id: int | None, seat_travellers: int, base_amount):
    """Supplier-defined group-size discount, scoped to the whole Tour (not a
    single TourPricing slab) - see TourGroupDiscountTier. Applied once to
    base_amount by total seat-paying traveller count. Returns
    (tier_or_None, discount_amount, discount_ratio) where discount_ratio is
    discount_amount / base_amount (0 when there is nothing to discount) -
    kept alongside the dollar amount so the same tier can be applied
    proportionally to the supplier's raw (pre-markup) share later, without
    re-deriving it from a dollar amount computed against a different base."""
    if not tour_id or seat_travellers <= 0 or money(base_amount) <= 0:
        return None, money(0), money(0)
    tier = (
        db.query(TourGroupDiscountTier)
        .filter(
            TourGroupDiscountTier.tour_id == tour_id,
            TourGroupDiscountTier.status == "active",
            TourGroupDiscountTier.min_pax <= seat_travellers,
            TourGroupDiscountTier.max_pax >= seat_travellers,
        )
        .first()
    )
    if not tier:
        return None, money(0), money(0)
    if tier.discount_type == "percentage":
        amount = money(base_amount) * money(tier.discount_value) / money(100)
    else:
        amount = money(tier.discount_value)
    amount = min(money(amount), money(base_amount))
    ratio = amount / money(base_amount)
    return tier, amount, ratio


def compute_supplier_commission_breakdown(raw_supplier_amount, group_discount_ratio, commission_percentage):
    """Pure calculation shared by real booking acceptance (supplier_accept_booking),
    the ledger, and the supplier-facing commission calculator endpoint, so
    those three can never disagree on the arithmetic.

    group_discount_ratio is the fraction (0..1) of the customer-facing base
    amount a Tour's group discount removed - see _resolve_group_discount.
    Applying the same ratio to the supplier's own raw amount means a
    discount defined once at the Tour level reduces both what the customer
    pays and what the supplier earns from consistently."""
    raw_supplier_amount = money(raw_supplier_amount)
    group_discount_ratio = money(group_discount_ratio or 0)
    commission_percentage = money(commission_percentage)
    discounted_amount = max(money(0), raw_supplier_amount * (money(1) - group_discount_ratio))
    group_discount_amount = raw_supplier_amount - discounted_amount
    commission_amount = money(discounted_amount * commission_percentage / money(100))
    net_earnings = discounted_amount - commission_amount
    return {
        "gross_amount": raw_supplier_amount,
        "group_discount_amount": group_discount_amount,
        "discounted_amount": discounted_amount,
        "commission_percentage": commission_percentage,
        "commission_amount": commission_amount,
        "net_earnings": net_earnings,
    }


def compute_booking_supplier_financials(db: Session, booking: Booking) -> dict | None:
    """Supplier gross / commission / net payable for a booking, read from the
    booking's locked financial snapshot (see _apply_commission_snapshot).
    Never re-reads the tour's current slab, date price or commission
    settings, so the ledger created at supplier acceptance, the admin
    breakdown and reports always show the figures fixed at booking time.

    Bookings created before the snapshot existed (financials_locked_at is
    None) get the same split computed from their own stored amounts, with
    the percentage resolved once; supplier_accept_booking then locks it.
    Tax, service fee, gateway fee and agent markup never enter these
    figures. Returns None when the booking has no supplier assigned."""
    if not booking.supplier_id:
        return None
    currency = booking.currency or "USD"
    customer_price = money(booking.customer_selling_price or booking.final_amount or booking.total_cost or 0)
    if booking.financials_locked_at is not None and booking.supplier_net_payable is not None:
        gross = money(booking.supplier_gross_amount if booking.supplier_gross_amount is not None else money(booking.supplier_net_payable) + money(booking.tourvaa_commission_amount or 0))
        return {
            "currency": currency,
            "gross_amount": gross,
            "commission_base_amount": money(booking.commission_base_amount or 0),
            "commission_percentage": money(booking.tourvaa_commission_percentage or 0),
            "commission_amount": money(booking.tourvaa_commission_amount or 0),
            "net_payable": money(booking.supplier_net_payable),
            "customer_price": customer_price,
            "customer_price_currency": currency,
        }

    if booking.tourvaa_commission_percentage is not None:
        pct = money(booking.tourvaa_commission_percentage)
    else:
        slab = db.query(TourPricing).filter(TourPricing.id == booking.pricing_slab_id).first() if booking.pricing_slab_id else None
        supplier = db.query(Supplier).filter(Supplier.id == booking.supplier_id).first()
        tour = db.query(Tour).filter(Tour.id == booking.tour_id).first() if booking.tour_id else None
        pct = resolve_effective_commission_percentage(db, tour=tour, supplier=supplier, slab=slab)
    split = _booking_financial_split(booking, pct)
    return {
        "currency": currency,
        "gross_amount": split["supplier_gross_amount"],
        "commission_base_amount": split["commission_base_amount"],
        "commission_percentage": split["commission_percentage"],
        "commission_amount": split["commission_amount"],
        "net_payable": split["supplier_net_payable"],
        "customer_price": customer_price,
        "customer_price_currency": currency,
    }

def _bookable_calendar_capacity(tour: Tour | None, calendar: TourCalendar) -> int:
    """Effective sellable capacity for a departure.

    Calendar capacity may be higher than a tour's group limit on legacy
    schedules. The public page and every booking path must treat the lower
    value as the total sellable capacity for that departure.
    """
    capacity = int(calendar.available_seats or 0)
    group_limit = int(tour.max_group_size or 0) if tour else 0
    if group_limit:
        return min(capacity, group_limit) if capacity else group_limit
    return capacity


def _price_booking(db: Session, data: BookingCreate, lock_calendar: bool = False, consume_discount: bool = False, pricing_details: dict | None = None):
    """Price a booking. When pricing_details (a dict) is passed it is filled
    with the resolved price source, unit prices and group-discount base so
    the caller can store them in the booking's financial snapshot."""
    adults = data.adults_count if data.adults_count is not None else data.no_of_adults
    children = data.children_count if data.children_count is not None else data.no_of_children
    seat_travellers = adults + children
    total_travellers = seat_travellers + data.no_of_infants
    if seat_travellers <= 0:
        raise HTTPException(status_code=400, detail="At least one traveller is required")

    tour = db.query(Tour).filter(Tour.id == data.tour_id).first() if data.tour_id else None
    calendar = None
    if data.tour_calendar_id:
        calendar_query = db.query(TourCalendar).filter(TourCalendar.id == data.tour_calendar_id)
        if lock_calendar:
            calendar_query = calendar_query.with_for_update()
        calendar = calendar_query.first()
    if data.tour_id and not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    if tour and tour.status != "published":
        raise HTTPException(status_code=400, detail="Tour must be published before booking")
    if tour and tour.max_group_size and seat_travellers > tour.max_group_size:
        raise HTTPException(
            status_code=400,
            detail=f"This tour allows a maximum of {tour.max_group_size} travellers per booking",
        )
    if calendar:
        if calendar.tour_id != data.tour_id:
            raise HTTPException(status_code=400, detail="Calendar date does not belong to tour")
        if calendar.status not in {"available", "active"}:
            raise HTTPException(status_code=400, detail="Selected tour date is not available")
        effective_capacity = _bookable_calendar_capacity(tour, calendar)
        if effective_capacity and calendar.booked_seats + seat_travellers > effective_capacity:
            raise HTTPException(status_code=409, detail="Not enough seats available")
    if data.tour_id:
        # Check both the requested start date and the selected calendar
        # departure: a request carrying only tour_calendar_id (no explicit
        # start date) must not bypass the blackout list.
        blackout_dates = set()
        if data.tour_start_date:
            blackout_dates.add(_parse_dt(data.tour_start_date).date())
        if calendar and calendar.tour_date:
            blackout_dates.add(calendar.tour_date.date())
        if blackout_dates:
            blocked = db.query(TourUnavailableDate).filter(
                TourUnavailableDate.tour_id == data.tour_id,
                func.date(TourUnavailableDate.unavailable_date).in_(blackout_dates),
            ).first()
            if blocked:
                raise HTTPException(status_code=400, detail="Selected date is unavailable")

    slab = None
    if data.tour_id:
        # Ordered (narrowest range, then newest) rather than an unordered
        # .first() -- new slabs are validated against overlap at creation
        # (services.tours._assert_no_pricing_overlap), but this keeps
        # resolution deterministic for any pre-existing overlapping slabs.
        slab = (
            db.query(TourPricing)
            .filter(TourPricing.tour_id == data.tour_id, TourPricing.status == "active", TourPricing.passenger_from <= seat_travellers, TourPricing.passenger_to >= seat_travellers)
            .order_by((TourPricing.passenger_to - TourPricing.passenger_from).asc(), TourPricing.id.desc())
            .first()
        )
        if not slab:
            # Tours priced via slabs must have a slab covering the requested
            # traveller count. Falling back silently here used to price
            # adults off the tour's starting price and children at 0 -
            # i.e. free children - for any count outside every defined
            # band. If the tour has slabs configured at all, treat an
            # out-of-range count as a hard error instead of guessing.
            has_any_slab = db.query(TourPricing.id).filter(TourPricing.tour_id == data.tour_id, TourPricing.status == "active").first() is not None
            if has_any_slab:
                raise HTTPException(status_code=400, detail=f"No pricing available for {seat_travellers} traveller(s) on this tour. Please choose a different traveller count or contact support.")
    # The booking's real transaction currency is always the tour/slab's
    # configured currency -- never the browsing/display currency the
    # customer's frontend happened to be showing converted amounts in
    # (data.currency, used only as a last-resort fallback when there's no
    # tour/slab to price against at all). This is deliberate: it's the
    # currency the payment gateway actually charges, the supplier is
    # actually paid in, and every downstream view (admin, invoice, supplier
    # ledger) consistently reads from booking.currency -- switching this to
    # the customer's ambient display currency would require rate-locked
    # re-pricing of every line item and gateway-side currency support
    # checks, and would leave the supplier settlement currency inconsistent
    # with what was actually charged. The customer-facing UI discloses the
    # real charge currency explicitly when it differs from what they were
    # browsing in (see the booking page's price breakdown).
    currency = slab.currency if slab else (tour.currency if tour else data.currency)
    # Supplier prices first (slab, or a per-date override of it). An active
    # supplier discount reduces these units BEFORE Tourvaa markup. Tourvaa's
    # own discount is resolved later against the marked-up storefront subtotal.
    from app.services.markup import effective_markup_percentage
    markup_percentage = money(effective_markup_percentage(db, slab)) if slab else money(0)
    supplier_adult_unit = money(slab.adult_price if slab else (tour.price_start_per_person if tour else 0))
    supplier_child_unit = money(slab.child_price if slab else 0)
    price_source = "SLAB" if slab else "TOUR_BASE"
    date_override = _resolve_date_price(db, data.tour_id, calendar.tour_date if calendar else data.tour_start_date)
    if date_override:
        supplier_adult_unit = money(date_override.adult_price)
        supplier_child_unit = money(date_override.child_price)
        price_source = "DATE_OVERRIDE"
    supplier_adult_original_unit = supplier_adult_unit
    supplier_child_original_unit = supplier_child_unit
    discount_travel_date = calendar.tour_date if calendar and calendar.tour_date else _parse_dt(data.tour_start_date)
    if slab and tour:
        from app.services.discounts import find_active_discount_stack, discount_amount_for
        supplier_discount = find_active_discount_stack(db, tour, lock=consume_discount, effective_at=discount_travel_date)["supplier"]
        raw_supplier_total = money(supplier_adult_unit * adults + supplier_child_unit * children)
        if supplier_discount and raw_supplier_total >= money(supplier_discount.minimum_booking_amount or 0):
            supplier_discount_amount = min(
                money(discount_amount_for(supplier_discount, float(raw_supplier_total))),
                raw_supplier_total,
            )
            if supplier_discount_amount > 0 and raw_supplier_total > 0:
                supplier_factor = (raw_supplier_total - supplier_discount_amount) / raw_supplier_total
                supplier_adult_unit = money(supplier_adult_unit * supplier_factor)
                supplier_child_unit = money(supplier_child_unit * supplier_factor)
                if consume_discount:
                    supplier_discount.used_count = (supplier_discount.used_count or 0) + 1
    adult_unit = apply_markup(supplier_adult_unit, markup_percentage)
    child_unit = apply_markup(supplier_child_unit, markup_percentage)
    per_person_amount = money(adult_unit * adults + child_unit * children)
    # Expose the customer-visible value of the supplier-funded offer in a
    # quote.  This is presentation data only: supplier discounts still apply
    # before markup and no booking calculation changes here.
    original_per_person_amount = money(
        apply_markup(supplier_adult_original_unit, markup_percentage) * adults
        + apply_markup(supplier_child_original_unit, markup_percentage) * children
    )
    supplier_offer_discount_amount = max(
        money(0), original_per_person_amount - per_person_amount
    )
    supplier_per_person_amount = money(supplier_adult_unit * adults + supplier_child_unit * children)
    # Group discount is a percentage of the seat-paying (adult+child) price
    # only -- infants and the solo single-supplement below are resolved
    # after this call so the discount % is never applied to them.
    group_tier, group_discount_amount, group_discount_ratio = _resolve_group_discount(db, data.tour_id, seat_travellers, per_person_amount)
    group_discount_funded_by = (group_tier.funded_by or "SUPPLIER") if group_tier else None
    infant_unit = money(getattr(tour, "infant_price", 0) or 0) if tour else money(0)
    infant_total = money(infant_unit * data.no_of_infants)
    # Single supplement: a lone adult (no children, no co-travellers) is
    # charged the tour's solo-occupancy surcharge on top of the per-person
    # price, matching standard travel-industry practice.
    single_supplement_amount = money(getattr(tour, "single_supplement", 0) or 0) if tour and seat_travellers == 1 else money(0)
    base_amount = money(per_person_amount + infant_total + single_supplement_amount)
    # Same traveller amount at the supplier's own prices (no markup): what
    # settlement is based on (compute_booking_financial_split). Infants and
    # the single supplement are tour-level amounts, not marked up.
    supplier_base_amount = money(supplier_per_person_amount + infant_total + single_supplement_amount)
    if pricing_details is not None:
        pricing_details.update({
            "price_source": price_source,
            "date_price_id": date_override.id if date_override else None,
            "admin_markup_percentage": markup_percentage,
            "supplier_base_amount": supplier_base_amount,
            "supplier_offer_discount_amount": supplier_offer_discount_amount,
            "adult_unit_price": adult_unit,
            "child_unit_price": child_unit,
            "infant_unit_price": infant_unit,
            "single_supplement_amount": single_supplement_amount,
            "group_discount_base_amount": per_person_amount if group_tier else None,
            "group_discount_percentage": (group_discount_ratio * 100).quantize(Decimal("0.0001")) if group_tier else None,
        })

    # Nights, for accommodation/extension extras priced per night. Only
    # resolvable when both ends of the stay are known; a *_per_night item is
    # rejected below rather than silently guessed at 1 night when they aren't.
    _trip_start = _parse_dt(data.tour_start_date)
    _trip_end = _parse_dt(data.tour_end_date)
    nights = (_trip_end - _trip_start).days if _trip_start and _trip_end else None
    room_count = data.no_of_rooms or 1

    def _addon_quantity(price_type: str, requested_quantity: int, *, label: str) -> int:
        if price_type == "per_person":
            return seat_travellers
        if price_type == "per_room":
            return room_count
        if price_type in {"per_person_per_night", "per_room_per_night"}:
            if not nights or nights < 1:
                raise HTTPException(status_code=400, detail=f"{label} is priced per night, but this booking has no resolvable number of nights (tour_start_date/tour_end_date required)")
            return (seat_travellers if price_type == "per_person_per_night" else room_count) * nights
        return requested_quantity

    # Two mutually-exclusive per-item margin models: cost-plus
    # (row.supplier_cost set -- supplier paid exactly quantity * supplier_cost,
    # no commission %, Tourvaa's margin is customer price minus that) takes
    # priority over the older commissionable/commission-percentage flag,
    # which only applies when supplier_cost is unset. cost_plus_customer_total
    # is the customer-price portion of cost-plus items (carved out of the
    # commissionable base in compute_booking_supplier_financials, exactly
    # like non_commissionable_addon_total) and cost_plus_supplier_total is
    # what the supplier is actually owed for those same items (added back in
    # full, in place of a customer-price add-back, since the payout there
    # isn't "customer price minus 0 commission" but the supplier's own cost).
    activity_rows = []
    activity_total = money(0)
    non_commissionable_addon_total = money(0)
    cost_plus_customer_total = money(0)
    cost_plus_supplier_total = money(0)
    for item in data.optional_activities:
        row = db.query(TourOptionalActivity).filter(TourOptionalActivity.id == item.id, TourOptionalActivity.status == "active").first() if item.id else None
        if not row or (data.tour_id and row.tour_id != data.tour_id):
            raise HTTPException(status_code=400, detail="Invalid optional activity")
        if row.pricing_mode == "per_passenger_type":
            # Ignores the client-supplied quantity entirely -- the booking's
            # own passenger counts are authoritative, same as accommodation's
            # per_person auto-quantity above. A null child/infant price
            # means "not priced separately": child falls back to the adult
            # rate, infant falls back to free (0) -- deliberate opt-in, see
            # OptionalActivityPayload.
            adult_unit = money(row.price_per_person)
            child_unit = money(row.child_price_per_person) if row.child_price_per_person is not None else adult_unit
            infant_unit = money(row.infant_price_per_person) if row.infant_price_per_person is not None else money(0)
            total = money(adult_unit * adults + child_unit * children + infant_unit * data.no_of_infants)
            activity_total += total
            item_qty = adults + children + data.no_of_infants
            if row.supplier_cost is not None:
                cost_plus_customer_total += total
                cost_plus_supplier_total += money(row.supplier_cost) * item_qty
            elif not row.commissionable:
                non_commissionable_addon_total += total
            activity_rows.append((row, item_qty, adult_unit, total))
        else:
            unit = money(row.price_per_person)
            total = money(unit * item.quantity)
            activity_total += total
            if row.supplier_cost is not None:
                cost_plus_customer_total += total
                cost_plus_supplier_total += money(row.supplier_cost) * item.quantity
            elif not row.commissionable:
                non_commissionable_addon_total += total
            activity_rows.append((row, item.quantity, unit, total))

    # Accommodation booking is out of scope for launch (frontend selection UI
    # is hidden behind SHOW_ACCOMMODATION_BOOKING = false). Reject rather than
    # silently accept, so a direct API call can't create a booking with
    # accommodation add-ons the product doesn't support end-to-end yet. The
    # underlying TourAccommodationExtra content-management (CMS) feature is
    # untouched -- this only blocks selecting extras *at booking time*.
    if data.accommodations:
        raise HTTPException(status_code=400, detail="Accommodation add-ons are not available for booking at this time")

    accommodation_rows = []
    accommodation_total = money(0)
    for item in data.accommodations:
        row = db.query(TourAccommodationExtra).filter(TourAccommodationExtra.id == item.id, TourAccommodationExtra.status == "active").first() if item.id else None
        if not row or (data.tour_id and row.tour_id != data.tour_id):
            raise HTTPException(status_code=400, detail="Invalid accommodation extra")
        unit = money(row.extra_price)
        qty = _addon_quantity(row.price_type, item.quantity, label=f"Accommodation extra '{row.accommodation_name}'")
        total = money(unit * qty)
        accommodation_total += total
        if row.supplier_cost is not None:
            cost_plus_customer_total += total
            cost_plus_supplier_total += money(row.supplier_cost) * qty
        elif not row.commissionable:
            non_commissionable_addon_total += total
        accommodation_rows.append((row, qty, unit, total))

    extension_rows = []
    extension_total = money(0)
    for item in data.extensions:
        row = db.query(TourExtension).filter(TourExtension.id == item.id, TourExtension.status == "active").first() if item.id else None
        if not row or (data.tour_id and row.tour_id != data.tour_id):
            raise HTTPException(status_code=400, detail="Invalid tour extension")
        unit = money(row.extra_price)
        qty = _addon_quantity(row.price_type, item.quantity, label=f"Extension '{row.extension_title}'")
        total = money(unit * qty)
        extension_total += total
        if row.supplier_cost is not None:
            cost_plus_customer_total += total
            cost_plus_supplier_total += money(row.supplier_cost) * qty
        elif not row.commissionable:
            non_commissionable_addon_total += total
        extension_rows.append((row, qty, unit, total))

    # Group and promotional discounts apply to the tour fare only. Extras are
    # separately selected products, so they must never increase the value of a
    # tour offer or be discounted by it.
    discounted_tour_amount = money(base_amount - group_discount_amount)
    addon_total = money(activity_total + accommodation_total + extension_total)
    discount, promo_discount_funded_by = _resolve_discount(
        db,
        data.promo_code,
        tour,
        discounted_tour_amount,
        consume=consume_discount,
        travel_date=discount_travel_date,
    )
    # Tax remains payable on the full selected order, after the tour-only
    # discount; service_fee is a flat per-booking amount.
    taxable_amount = money(discounted_tour_amount - discount + addon_total)
    tax_percentage = money(getattr(tour, "tax_percentage", 0) or 0) if tour else money(0)
    tax = money(taxable_amount * tax_percentage / money(100)) if tax_percentage > 0 else money(0)
    service_fee = money(getattr(tour, "service_fee", 0) or 0) if tour else money(0)
    # Gateway fee is a percentage of the taxed subtotal so the displayed
    # total matches what the payment gateway (Stripe/PayPal) actually
    # deducts, instead of only carrying the flat service_fee (see ID 04 in
    # pricing-audit/07-pricing-bugs.md).
    gateway_fee_percentage = money(getattr(tour, "gateway_fee_percentage", 0) or 0) if tour else money(0)
    gateway_fee = money((taxable_amount + tax) * gateway_fee_percentage / money(100)) if gateway_fee_percentage > 0 else money(0)
    surcharge = money(service_fee + gateway_fee)
    final = money(discounted_tour_amount + addon_total - discount + tax + surcharge)
    if final < 0:
        raise HTTPException(status_code=400, detail="Final amount cannot be negative")
    return tour, calendar, adults, children, total_travellers, currency, base_amount, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activity_rows, accommodation_rows, extension_rows, slab, group_tier, group_discount_amount, group_discount_funded_by, promo_discount_funded_by, service_fee, gateway_fee, non_commissionable_addon_total, cost_plus_customer_total, cost_plus_supplier_total


def calculate_booking_price(db: Session, data: BookingCreate) -> dict:
    pricing_details: dict = {}
    tour, calendar, adults, children, total_travellers, currency, base, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activities, accommodations, extensions, slab, group_tier, group_discount_amount, group_discount_funded_by, promo_discount_funded_by, service_fee, gateway_fee, non_commissionable_addon_total, cost_plus_customer_total, cost_plus_supplier_total = _price_booking(db, data, pricing_details=pricing_details)
    # Agents are commission-only by default (see AgentLedger /
    # compute_booking_supplier_financials) -- markup only applies if an
    # admin has explicitly opted in via the allow_agent_markup setting (off
    # by default), never combined silently with agent commission.
    agent_markup = money(data.agent_markup) if data.booking_source == "agent" and get_allow_agent_markup(db) else money(0)
    customer_selling_price = money(final + agent_markup)
    return {
        "tour_id": data.tour_id,
        "tour_calendar_id": data.tour_calendar_id,
        "currency": currency,
        "adult_count": adults,
        "child_count": children,
        "total_passengers": total_travellers,
        "base_amount": money_str(base),
        "optional_activity_amount": money_str(activity_total),
        "accommodation_amount": money_str(accommodation_total),
        "extension_amount": money_str(extension_total),
        "group_discount_tier_id": group_tier.id if group_tier else None,
        "group_discount_amount": money_str(group_discount_amount),
        "supplier_offer_discount_amount": money_str(
            pricing_details.get("supplier_offer_discount_amount", 0)
        ),
        "group_discount_funded_by": group_discount_funded_by,
        "discount_amount": money_str(discount),
        "promo_discount_funded_by": promo_discount_funded_by,
        "tax_amount": money_str(tax),
        "surcharge_amount": money_str(surcharge),
        "service_fee_amount": money_str(service_fee),
        "gateway_fee_amount": money_str(gateway_fee),
        "final_amount": money_str(customer_selling_price),
        "agent_net_price": money_str(final),
        "agent_markup": money_str(agent_markup),
        "customer_selling_price": money_str(customer_selling_price),
        "available": True,
        "tour_name": tour.title if tour else data.tour_name,
        "tour_date": calendar.tour_date.date().isoformat() if calendar and calendar.tour_date else data.tour_date,
        "line_items": {
            "optional_activities": [{"id": row.id, "name": row.activity_name, "quantity": qty, "unit_price": money_str(unit), "total_price": money_str(total)} for row, qty, unit, total in activities],
            "accommodations": [{"id": row.id, "name": row.accommodation_name, "quantity": qty, "unit_price": money_str(unit), "total_price": money_str(total)} for row, qty, unit, total in accommodations],
            "extensions": [{"id": row.id, "name": row.extension_title, "quantity": qty, "unit_price": money_str(unit), "total_price": money_str(total)} for row, qty, unit, total in extensions],
        },
    }


def get_bookings(db: Session, page: int = 1, limit: int = 20, search: str = "", customer_id: Optional[int] = None, booking_status: str = "", payment_status: str = "", supplier_acceptance_status: str = "", country_id: Optional[int] = None, supplier_id: Optional[int] = None, agent_id: Optional[int] = None, tour_id: Optional[int] = None, start_date: str = "", end_date: str = "", sort_by: str = "newest", actor: Optional[User] = None) -> dict:
    query = db.query(Booking).options(joinedload(Booking.customer))
    # Gateway checkout needs a booking ID before redirecting to Stripe/PayPal.
    # Until money is received that row is only a provisional checkout record,
    # not a user-visible booking. Hiding it here keeps abandoned/back-button
    # checkouts out of customer, supplier, agent and admin booking lists. Paid
    # and partially-paid bookings remain visible even if their workflow status
    # has not advanced yet.
    query = query.filter(
        or_(
            Booking.booking_status != "pending_payment",
            Booking.payment_status.notin_(("unpaid", "pending")),
        )
    )
    # A customer may discard a provisional unpaid checkout. Keep that audit
    # record out of every portal, just like an abandoned pending-payment row;
    # paid bookings always follow the visible cancellation/refund workflow.
    query = query.filter(
        or_(
            Booking.cancellation_source.is_(None),
            Booking.cancellation_source != "customer_unpaid_removed",
        )
    )
    role = _user_role(actor)
    if role == "supplier":
        query = query.join(Booking.supplier).filter_by(user_id=actor.id)
        # Keep withdrawals available to Operations for reassignment and any
        # contractual-liability review, but remove them from the withdrawing
        # supplier's actionable booking queue as soon as they are submitted.
        query = query.filter(Booking.booking_status != "supplier_reassignment_required")
    elif role == "agent":
        query = query.join(Booking.agent).filter_by(user_id=actor.id)
    elif role == "customer":
        query = query.join(Booking.customer).filter_by(user_id=actor.id)
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(or_(Booking.booking_code.ilike(pattern), Booking.tour_name.ilike(pattern), Booking.country.ilike(pattern), Booking.supplier_name.ilike(pattern)))
    if customer_id:
        query = query.filter(Booking.customer_id == customer_id)
    if payment_status:
        query = query.filter(Booking.payment_status == payment_status.strip().lower())
    if supplier_acceptance_status:
        query = query.filter(Booking.supplier_acceptance_status == supplier_acceptance_status.strip().lower())
    if country_id:
        query = query.filter(Booking.country_id == country_id)
    if supplier_id:
        query = query.filter(Booking.supplier_id == supplier_id)
    if agent_id:
        query = query.filter(Booking.agent_id == agent_id)
    if tour_id:
        query = query.filter(Booking.tour_id == tour_id)
    if start_date:
        query = query.filter(Booking.created_at >= start_date)
    if end_date:
        query = query.filter(Booking.created_at <= f"{end_date} 23:59:59")
    status_counts = {
        status: count
        for status, count in query.enable_eagerloads(False).with_entities(Booking.booking_status, func.count(Booking.id))
        .group_by(Booking.booking_status)
        .all()
    }
    if booking_status:
        query = query.filter(Booking.booking_status == booking_status.strip().lower())
    query = query.order_by(Booking.id.asc() if sort_by == "oldest" else Booking.id.desc())
    total = query.count()
    items = [serialize_booking_for_actor(db, b, actor, detail=False) for b in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit)), "status_counts": status_counts}


def get_booking_detail(db: Session, booking_id: int, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    log_audit(db, actor=actor, action="view_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit()
    role = _user_role(actor)
    data = serialize_booking(
        db, booking, detail=True,
        include_supplier_breakdown=role == "admin",
        hide_supplier_identity=role in ("customer", "agent"),
    )
    if role in ("admin", "agent"):
        data["agent_payment_summary"] = _agent_payment_summary(db, booking)
    if role == "agent":
        from app.services.cancellations import customer_cancellation_eligibility
        data["cancellation_eligibility"] = customer_cancellation_eligibility(db, booking)
    if role == "supplier":
        from app.services.cancellations import supplier_cancellation_terms
        data = _supplier_safe(data, booking)
        data["supplier_payment_summary"] = _supplier_payment_summary(db, booking)
        data["supplier_cancellation_terms"] = supplier_cancellation_terms(db, booking)
    else:
        data = _hide_supplier_reassignment_from_external_partner(data, booking, role)
    return data


def _validate_customer_travellers(data: BookingCreate, adults: int, children: int) -> None:
    if data.booking_source not in {"customer", "agent"}:
        return
    if not data.travellers:
        raise HTTPException(status_code=400, detail="Traveller details are required for customer and agent bookings")

    adult_rows = [row for row in data.travellers if row.traveller_type == "adult"]
    child_rows = [row for row in data.travellers if row.traveller_type == "child"]
    if len(adult_rows) != adults or len(child_rows) != children:
        raise HTTPException(status_code=400, detail="Traveller details must match the selected adult and child counts")
    if sum(1 for row in data.travellers if row.is_primary_contact) != 1:
        raise HTTPException(status_code=400, detail="Exactly one traveller must be the primary contact")

    for row in data.travellers:
        full_name = (row.full_name or f"{row.first_name} {row.last_name}").strip()
        if not full_name:
            raise HTTPException(status_code=400, detail="Every traveller must have a full name")
        if row.age is None:
            raise HTTPException(status_code=400, detail="Every traveller must have an age")
        if row.traveller_type == "adult" and not 12 <= row.age <= 120:
            raise HTTPException(status_code=400, detail="Adult traveller age must be between 12 and 120")
        if row.traveller_type == "child" and not 3 <= row.age <= 11:
            raise HTTPException(status_code=400, detail="Child traveller age must be between 3 and 11")


def _validate_agreements(db: Session, data: BookingCreate, tour) -> None:
    """Enforces the booking flow's Review-step accept/agree checkboxes
    server-side -- the frontend already disables the submit button on these,
    but that alone doesn't stop a direct API call from skipping them."""
    if data.booking_source not in {"customer", "agent"}:
        return
    if not data.agreed_terms:
        raise HTTPException(status_code=400, detail="You must agree to the booking terms and cancellation policy to continue")
    if tour and tour.id:
        from app.models.cancellations import RefundRule
        has_policy = db.query(RefundRule.id).filter(RefundRule.tour_id == tour.id).first() is not None
        if has_policy and not data.agreed_cancellation_policy:
            raise HTTPException(status_code=400, detail="You must agree to this tour's cancellation & refund policy to continue")


def create_booking(db: Session, data: BookingCreate, actor: Optional[User] = None, request: Optional[Request] = None, background_tasks: BackgroundTasks | None = None) -> dict:
    # Portal users may only create bookings in their own role. In particular,
    # a customer must never be able to attach an Agent ID (or spoof an agent
    # booking source) through a crafted request. An agent booking deliberately
    # has two parties: the agent who created it and the selected customer.
    # Traveller email addresses never establish the Agent relationship.
    if actor and _user_role(actor) == "customer":
        if data.booking_source != "customer" or data.agent_id is not None:
            raise HTTPException(status_code=403, detail="Customers cannot create or attach agent bookings")
    if data.booking_source == "customer" and not data.customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required for customer bookings")
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if data.booking_source == "customer" and actor and _user_role(actor) == "customer" and customer.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Customer booking access denied")
    if actor and _user_role(actor) == "agent":
        from app.services.agent_scope import ensure_agent_customer_access
        ensure_agent_customer_access(db, data.customer_id, actor)
        agent = db.query(Agent).filter(Agent.user_id == actor.id).first()
        if not agent:
            raise HTTPException(status_code=403, detail="Agent profile not found")
        # The authenticated identity is authoritative. Never trust a portal
        # caller to choose another agent or disguise the booking source.
        data.agent_id = agent.id
        data.booking_source = "agent"
    if data.booking_source == "agent" and not data.agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required for agent bookings")

    # Affiliate attribution: never trust a raw client-supplied affiliate_id
    # for self-service callers (customer/agent portals) - that would let
    # anyone claim commission for any affiliate by just passing an id. Only
    # a real, active referral link's ref_code can attach an affiliate. Admins
    # (trusted actors) may still assign affiliate_id directly, e.g. to credit
    # an offline referral.
    resolved_affiliate_id = None
    resolved_affiliate_ref_code = None
    resolved_attribution = None
    if data.affiliate_ref_code:
        from app.services.affiliate_tracking import resolve_affiliate_link
        link = resolve_affiliate_link(db, data.affiliate_ref_code)
        if link:
            resolved_affiliate_id = link.affiliate_id
            resolved_affiliate_ref_code = link.ref_code
    elif data.affiliate_id and _user_role(actor) == "admin":
        resolved_affiliate_id = data.affiliate_id
    else:
        # Fall back to the server-tracked attribution cookie set by
        # GET /r/{code} - covers the common case of "clicked a link, booked
        # later without the app re-sending ref_code". Never allowed to break
        # booking creation: any failure here is swallowed and the booking
        # just proceeds with no affiliate attached.
        try:
            from app.services.affiliate_tracking import resolve_attribution_from_request
            resolved_attribution = resolve_attribution_from_request(db, request)
            if resolved_attribution:
                resolved_affiliate_id = resolved_attribution.affiliate_id
                resolved_affiliate_ref_code = resolved_attribution.link.ref_code if resolved_attribution.link else None
        except Exception:
            logger.warning("Affiliate attribution lookup failed for booking creation", exc_info=True)

    pricing_details: dict = {}
    tour, calendar, adults, children, total_travellers, currency, base, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activities, accommodations, extensions, slab, group_tier, group_discount_amount, group_discount_funded_by, promo_discount_funded_by, service_fee, gateway_fee, non_commissionable_addon_total, cost_plus_customer_total, cost_plus_supplier_total = _price_booking(db, data, lock_calendar=True, consume_discount=True, pricing_details=pricing_details)
    if tour:
        # calendar is only set when the caller passed tour_calendar_id - fall
        # back to the raw tour_date string (checkout/admin bookings that
        # book a date without pinning a specific calendar row) so the
        # advance-booking window is enforced either way.
        booked_date = calendar.tour_date if calendar and calendar.tour_date else (_parse_dt(data.tour_date) if data.tour_date else None)
        if booked_date:
            from app.services.tour_availability import assert_meets_advance_booking_window, agent_reserve_eligibility
            assert_meets_advance_booking_window(db, tour.id, booked_date)
            if data.booking_source == "agent" and data.agent_payment_method in {"pay_later", "credit"}:
                if not agent_reserve_eligibility(db, tour.id, booked_date)["eligible"]:
                    raise HTTPException(
                        status_code=400,
                        detail="This tour is now too close to departure for a no-deposit reservation -- pay in full to confirm this booking.",
                    )
    _validate_customer_travellers(data, adults, children)
    _validate_agreements(db, data, tour)
    country = db.query(Country).filter(Country.id == (data.country_id or (tour.country_id if tour else None))).first() if (data.country_id or tour) else None
    city = db.query(City).filter(City.id == (data.city_id or (tour.city_id if tour else None))).first() if (data.city_id or tour) else None
    supplier = tour.supplier if tour and tour.supplier else None
    supplier_id = data.supplier_id or (supplier.id if supplier else None)
    agent_net_price = final if data.booking_source == "agent" else money(0)
    # Commission-only by default -- see allow_agent_markup toggle at calculate_booking_price above.
    agent_markup = money(data.agent_markup) if data.booking_source == "agent" and get_allow_agent_markup(db) else money(0)
    customer_selling_price = money(final + agent_markup) if data.booking_source == "agent" else final
    payment_status = "pending"
    booking_status = "pending_payment"
    if data.booking_source == "agent" and data.agent_payment_method == "credit":
        payment_status = "credit_approval_pending"
        booking_status = "pending_credit_approval"
    elif data.booking_source == "agent" and data.agent_payment_method == "pay_later":
        payment_status = "credit_approval_pending"
        booking_status = "pending_credit_approval"
    elif data.booking_source == "agent" and data.agent_payment_method == "bank_transfer":
        payment_status = "bank_transfer_pending"
    booking = Booking(
        customer_id=data.customer_id, tour_id=data.tour_id, tour_calendar_id=data.tour_calendar_id, supplier_id=supplier_id, agent_id=data.agent_id, affiliate_id=resolved_affiliate_id, affiliate_ref_code=resolved_affiliate_ref_code, affiliate_attribution_id=resolved_attribution.id if resolved_attribution else None, created_by=actor.id if actor else None, booked_by_user_id=actor.id if actor else None, booking_source=data.booking_source, country_id=data.country_id or (tour.country_id if tour else None), city_id=data.city_id or (tour.city_id if tour else None),
        tour_name=(data.tour_name or (tour.title if tour else "")).strip(), tour_date=(data.tour_date or (calendar.tour_date.date().isoformat() if calendar and calendar.tour_date else "")).strip(), country=(data.country or (country.country_name if country else "")).strip(), supplier_name=(data.supplier_name or (supplier.supplier_name if supplier else "")).strip(), tour_start_date=_parse_dt(data.tour_start_date) or (calendar.tour_date if calendar else None), tour_end_date=_parse_dt(data.tour_end_date),
        no_of_adults=adults, no_of_children=children, no_of_infants=data.no_of_infants, no_of_rooms=data.no_of_rooms, adults_count=adults, children_count=children, total_travellers=total_travellers, currency=currency,
        total_cost=customer_selling_price, base_amount=base, optional_activity_amount=activity_total, accommodation_amount=accommodation_total, extension_amount=extension_total, non_commissionable_addon_amount=non_commissionable_addon_total, cost_plus_customer_amount=cost_plus_customer_total, cost_plus_supplier_payable=cost_plus_supplier_total, group_discount_tier_id=group_tier.id if group_tier else None, group_discount_amount=group_discount_amount, group_discount_funded_by=group_discount_funded_by, discount_amount=discount, promo_code=data.promo_code, promo_discount_funded_by=promo_discount_funded_by, tax_amount=tax, surcharge_amount=surcharge, service_fee_amount=service_fee, gateway_fee_amount=gateway_fee, final_amount=customer_selling_price, agent_net_price=agent_net_price, agent_markup=agent_markup, customer_selling_price=customer_selling_price, amount_paid=money(0), amount_pending=customer_selling_price,
        booking_status=booking_status, supplier_acceptance_status="pending" if supplier_id else "not_assigned", payment_status=payment_status, payment_type=data.payment_type, agent_payment_method=data.agent_payment_method if data.booking_source == "agent" else None, agent_reference=data.agent_reference if data.booking_source == "agent" else None, notes=data.notes, customer_notes=data.customer_notes, admin_notes=data.admin_notes,
        # Pricing/currency snapshot -- captured once here and never touched
        # again, even if the slab, commission, or exchange rates change
        # later. No live display-currency conversion happens at checkout
        # today, so display_currency/exchange_rate reflect "charged as-is"
        # rather than a real conversion; this is the hook a future
        # visitor-currency checkout flow would populate instead.
        pricing_slab_id=slab.id if slab else None,
        supplier_price=slab.adult_price if slab else None,
        supplier_currency=slab.currency if slab else None,
        tourvaa_selling_price=(slab.storefront_adult_price if slab else None),
        display_currency=currency,
        exchange_rate=money(1),
        exchange_rate_source="same_currency",
        exchange_rate_captured_at=utcnow(),
        converted_customer_amount=customer_selling_price,
    )
    db.add(booking)
    db.flush()
    booking.booking_code = _booking_code(db, booking.id, booking.booking_source)
    if resolved_attribution:
        resolved_attribution.booking_id = booking.id
        resolved_attribution.status = "consumed"
    if calendar:
        calendar.booked_seats += adults + children
    for t in data.travellers:
        full = t.full_name or f"{t.first_name} {t.last_name}".strip()
        db.add(BookingTraveller(booking_id=booking.id, traveller_type=t.traveller_type, first_name=t.first_name, last_name=t.last_name, full_name=full, age=t.age, gender=t.gender, nationality=t.nationality, passport_number=t.passport_number, email=t.email, phone=t.phone, is_primary_contact=1 if t.is_primary_contact else 0, special_requirements=t.special_requirements))
    for row, qty, unit, total in activities:
        db.add(BookingOptionalActivity(booking_id=booking.id, tour_optional_activity_id=row.id, activity_name_snapshot=row.activity_name, quantity=qty, unit_price=unit, total_price=total))
    for row, qty, unit, total in accommodations:
        db.add(BookingAccommodation(booking_id=booking.id, tour_accommodation_extra_id=row.id, accommodation_name_snapshot=row.accommodation_name, quantity=qty, price_type=row.price_type, unit_price=unit, total_price=total))
    for row, qty, unit, total in extensions:
        db.add(BookingExtension(booking_id=booking.id, tour_extension_id=row.id, extension_tour_id=row.extension_tour_id, extension_name_snapshot=row.extension_title, quantity=qty, unit_price=unit, total_price=total))
    _history(db, booking, None, booking.booking_status, actor, _user_role(actor), "Booking created")
    customer.total_bookings = (customer.total_bookings or 0) + 1
    customer.upcoming_bookings = (customer.upcoming_bookings or 0) + 1
    customer.total_amount_pending = money(customer.total_amount_pending or 0) + customer_selling_price
    log_audit(db, actor=actor, action="create_booking", entity_type="booking", entity_id=booking.id, new_values=serialize_booking(db, booking), request=request)
    from app.services.notifications import enqueue_notification
    if customer.user_id:
        enqueue_notification(db, user_id=customer.user_id, notification_type="booking_created", title="Booking created", message=f"Your booking {booking.booking_code} was created", entity_type="booking", entity_id=booking.id)

    _apply_commission_snapshot(db, booking, pricing_details)

    if booking.agent_id and booking.agent:
        from app.services.agent_ledger import create_ledger_entry
        commission_amount = booking.agent_commission_amount if booking.agent_commission_amount is not None else money(0)
        try:
            create_ledger_entry(
                db,
                booking=booking,
                agent_id=booking.agent_id,
                gross_amount=customer_selling_price,
                commission_amount=commission_amount,
                commission_percentage=booking.agent_commission_percentage,
            )
        except Exception as error:
            logger.warning("Agent ledger entry creation failed for booking %s: %s", booking.id, error)

    db.commit()
    db.refresh(booking)

    if booking.booking_source == "agent" and payment_status in {"credit_approval_pending", "bank_transfer_pending"}:
        # Agent "Reserve Now" -- no deposit taken, so an invoice for the full
        # outstanding amount is generated and emailed immediately rather than
        # waiting on the on-demand Download Invoice action. The agent who
        # made the reservation needs it just as much as the customer (they're
        # the one who owes Tourvaa, not the traveller), so it's sent to both.
        # Deliberately left synchronous (unlike the emails below): this is a
        # comparatively low-volume agent-only flow, and email_invoice_to_customer
        # is also called directly as an on-demand admin/customer action
        # elsewhere with a success/failure contract (it raises on delivery
        # failure) that backgrounding it here would silently break. It's
        # already wrapped in try/except so a failure here can't fail the
        # booking response either way.
        try:
            from app.schemas.invoices import InvoiceEmailRequest, InvoiceGenerateRequest
            from app.services.invoices import email_invoice_to_customer, generate_invoice
            invoice = generate_invoice(db, InvoiceGenerateRequest(booking_id=booking.id), actor, request)
            email_invoice_to_customer(db, invoice["id"], InvoiceEmailRequest(), actor, request)
            agent_email = _resolve_agent_invoice_email(db, booking.agent_id)
            if agent_email:
                email_invoice_to_customer(db, invoice["id"], InvoiceEmailRequest(email=agent_email), actor, request)
        except Exception:
            logger.warning("Reservation invoice generation/email failed for booking %s", booking.id, exc_info=True)

    # Every email below is scheduled (BackgroundTasks, or a daemon thread
    # fallback when none was threaded through - see _send_booking_email /
    # email_admins) rather than sent inline: booking success must never
    # depend on, or wait on, SMTP.
    from app.utils.email_templates import booking_confirmation_email
    login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
    _send_booking_email(
        db, "booking_confirmation",
        {"name": customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
         "tour_date": booking.tour_date or "", "adults": booking.adults_count, "currency": booking.currency,
         "total": booking.final_amount, "login_url": login_url, "button_text": "View booking", "button_url": login_url},
        f"Booking received - {booking.booking_code}",
        booking_confirmation_email(customer.full_name, booking.booking_code, booking.tour_name, booking.tour_date or "", booking.adults_count, booking.currency, booking.final_amount, login_url),
        customer.email,
        background_tasks=background_tasks,
    )


    return serialize_booking_for_actor(db, booking, actor)


def _recalculate_booking_price(db: Session, booking: Booking, data: BookingUpdate) -> None:
    """Rebuilds a booking's passenger counts, add-ons, and every derived price
    field from scratch through _price_booking -- the same function
    create_booking/calculate_booking_price use -- so an edited booking's total
    can never drift from what a fresh calculate-price call for the same
    inputs would produce. Only called when the request didn't also pass an
    explicit total_cost (see update_booking's ambiguity check)."""
    adults = data.no_of_adults if data.no_of_adults is not None else (booking.adults_count if booking.adults_count is not None else booking.no_of_adults)
    children = data.no_of_children if data.no_of_children is not None else (booking.children_count if booking.children_count is not None else booking.no_of_children)
    infants = data.no_of_infants if data.no_of_infants is not None else booking.no_of_infants

    def _existing_addons(rows, id_attr):
        return [BookingAddonPayload(id=getattr(row, id_attr), quantity=row.quantity) for row in rows if getattr(row, id_attr)]

    optional_activities = data.optional_activities if data.optional_activities is not None else _existing_addons(booking.optional_activities, "tour_optional_activity_id")
    accommodations = data.accommodations if data.accommodations is not None else _existing_addons(booking.accommodations, "tour_accommodation_extra_id")
    extensions = data.extensions if data.extensions is not None else _existing_addons(booking.extensions, "tour_extension_id")
    promo_code = data.promo_code if data.promo_code is not None else booking.promo_code

    booking_create = BookingCreate(
        customer_id=booking.customer_id,
        tour_id=booking.tour_id,
        tour_calendar_id=booking.tour_calendar_id,
        booking_source=booking.booking_source or "admin",
        tour_start_date=booking.tour_start_date.isoformat() if booking.tour_start_date else None,
        tour_end_date=booking.tour_end_date.isoformat() if booking.tour_end_date else None,
        no_of_adults=adults,
        no_of_children=children,
        no_of_infants=infants,
        no_of_rooms=booking.no_of_rooms,
        adults_count=adults,
        children_count=children,
        currency=booking.currency or "USD",
        promo_code=promo_code,
        optional_activities=optional_activities,
        accommodations=accommodations,
        extensions=extensions,
    )

    old_seat_travellers = (booking.adults_count if booking.adults_count is not None else booking.no_of_adults) + (booking.children_count if booking.children_count is not None else booking.no_of_children)
    calendar_row = None
    if booking.tour_calendar_id:
        # Net this booking's own already-booked seats out of the calendar
        # count before re-validating capacity, otherwise editing a booking
        # that already holds seats would double-count them against its own
        # new total and spuriously reject a perfectly fittable change.
        calendar_row = db.query(TourCalendar).filter(TourCalendar.id == booking.tour_calendar_id).with_for_update().first()
        if calendar_row:
            calendar_row.booked_seats = max(0, (calendar_row.booked_seats or 0) - old_seat_travellers)

    pricing_details: dict = {}
    tour, calendar, new_adults, new_children, total_travellers, currency, base, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activities, accommodation_rows, extension_rows, slab, group_tier, group_discount_amount, group_discount_funded_by, promo_discount_funded_by, service_fee, gateway_fee, non_commissionable_addon_total, cost_plus_customer_total, cost_plus_supplier_total = _price_booking(db, booking_create, lock_calendar=False, consume_discount=False, pricing_details=pricing_details)

    if calendar_row:
        calendar_row.booked_seats = (calendar_row.booked_seats or 0) + new_adults + new_children

    agent_net_price = final if booking.booking_source == "agent" else money(0)
    # Commission-only by default -- see allow_agent_markup toggle at calculate_booking_price above.
    # Recalc path: preserve the booking's existing agent_markup if markup is
    # allowed (an admin edit shouldn't silently wipe an already-set markup),
    # otherwise force 0.
    agent_markup = money(booking.agent_markup or 0) if booking.booking_source == "agent" and get_allow_agent_markup(db) else money(0)
    customer_selling_price = money(final + agent_markup) if booking.booking_source == "agent" else final

    booking.no_of_adults = new_adults
    booking.no_of_children = new_children
    booking.no_of_infants = infants
    booking.adults_count = new_adults
    booking.children_count = new_children
    booking.total_travellers = total_travellers
    booking.base_amount = base
    booking.optional_activity_amount = activity_total
    booking.accommodation_amount = accommodation_total
    booking.extension_amount = extension_total
    booking.non_commissionable_addon_amount = non_commissionable_addon_total
    booking.cost_plus_customer_amount = cost_plus_customer_total
    booking.cost_plus_supplier_payable = cost_plus_supplier_total
    booking.group_discount_tier_id = group_tier.id if group_tier else None
    booking.group_discount_amount = group_discount_amount
    booking.group_discount_funded_by = group_discount_funded_by
    booking.discount_amount = discount
    booking.promo_code = promo_code
    booking.promo_discount_funded_by = promo_discount_funded_by
    booking.tax_amount = tax
    booking.surcharge_amount = surcharge
    booking.service_fee_amount = service_fee
    booking.gateway_fee_amount = gateway_fee
    booking.total_cost = customer_selling_price
    booking.final_amount = customer_selling_price
    booking.agent_net_price = agent_net_price
    booking.agent_markup = agent_markup
    booking.customer_selling_price = customer_selling_price
    booking.amount_pending = max(money(0), customer_selling_price - money(booking.amount_paid or 0))
    booking.pricing_slab_id = slab.id if slab else None

    # Re-pricing is only allowed before any payment (see update_booking), so
    # re-locking the financial snapshot here is the one sanctioned change to
    # it. Keep the pending agent ledger entry in step with the new figure.
    _apply_commission_snapshot(db, booking, pricing_details)
    if booking.agent_id:
        from app.models.agent_ledger import AgentLedger
        entry = db.query(AgentLedger).filter(AgentLedger.booking_id == booking.id, AgentLedger.status == "pending").first()
        if entry:
            new_commission = money(booking.agent_commission_amount or 0)
            entry.gross_amount = customer_selling_price
            entry.commission_amount = new_commission
            entry.commission_percentage = money(
                booking.agent_commission_percentage
                if booking.agent_commission_percentage is not None
                else (new_commission / customer_selling_price) * 100 if customer_selling_price > 0 else 0
            )
            entry.net_payable = new_commission
            entry.amount_pending = max(money(0), new_commission - money(entry.amount_paid or 0))

    for existing in list(booking.optional_activities):
        db.delete(existing)
    for existing in list(booking.accommodations):
        db.delete(existing)
    for existing in list(booking.extensions):
        db.delete(existing)
    db.flush()
    for row, qty, unit, total in activities:
        db.add(BookingOptionalActivity(booking_id=booking.id, tour_optional_activity_id=row.id, activity_name_snapshot=row.activity_name, quantity=qty, unit_price=unit, total_price=total))
    for row, qty, unit, total in accommodation_rows:
        db.add(BookingAccommodation(booking_id=booking.id, tour_accommodation_extra_id=row.id, accommodation_name_snapshot=row.accommodation_name, quantity=qty, price_type=row.price_type, unit_price=unit, total_price=total))
    for row, qty, unit, total in extension_rows:
        db.add(BookingExtension(booking_id=booking.id, tour_extension_id=row.id, extension_tour_id=row.extension_tour_id, extension_name_snapshot=row.extension_title, quantity=qty, unit_price=unit, total_price=total))


def update_booking(db: Session, booking_id: int, data: BookingUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    if _user_role(actor) == "agent":
        agent_editable = {"notes", "customer_notes"}
        restricted = set(data.model_fields_set) - agent_editable
        if restricted:
            raise HTTPException(status_code=403, detail="Agents may only update booking notes")

    fields_set = set(data.model_fields_set)
    recalc_fields = {"no_of_adults", "no_of_children", "no_of_infants", "optional_activities", "accommodations", "extensions", "promo_code"}
    wants_recalc = bool(recalc_fields & fields_set)
    wants_manual_total = data.total_cost is not None

    if wants_recalc and wants_manual_total:
        raise HTTPException(
            status_code=400,
            detail="Pass either updated passenger/add-on selections to recalculate the price, or an explicit total_cost override -- not both in the same request.",
        )

    financial_fields = recalc_fields | {"total_cost"}
    if money(booking.amount_paid or 0) > money(0) and financial_fields & fields_set:
        raise HTTPException(
            status_code=409,
            detail="This booking already has a payment recorded, so its passenger counts, add-ons, and total cost can no longer be edited directly. Process a refund/adjustment or cancel and rebook instead.",
        )

    old_values = serialize_booking(db, booking)
    for field in ["tour_name", "tour_date", "country", "supplier_name", "notes", "customer_notes", "admin_notes"]:
        value = getattr(data, field)
        if value is not None:
            setattr(booking, field, value.strip() if isinstance(value, str) else value)
    for field in ["supplier_id", "agent_id", "affiliate_id"]:
        value = getattr(data, field)
        if value is not None:
            setattr(booking, field, value)

    if wants_recalc:
        _recalculate_booking_price(db, booking, data)
    elif wants_manual_total:
        new_total = money(data.total_cost)
        if new_total <= money(0):
            raise HTTPException(status_code=400, detail="total_cost must be a positive amount")
        booking.total_cost = new_total
        booking.final_amount = new_total
        if booking.booking_source == "agent":
            booking.customer_selling_price = new_total
            booking.agent_net_price = max(money(0), new_total - money(booking.agent_markup))
        else:
            booking.customer_selling_price = new_total
            booking.agent_net_price = money(0)
            booking.agent_markup = money(0)
        booking.amount_pending = max(money(0), new_total - money(booking.amount_paid))

    log_audit(db, actor=actor, action="update_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(db, booking), request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking_for_actor(db, booking, actor)


def update_booking_status(db: Session, booking_id: int, data: BookingStatusUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    if _user_role(actor) == "agent":
        raise HTTPException(status_code=403, detail="Agents cannot directly change booking status")
    _validate_booking_status_transition(booking.booking_status, data.booking_status)
    old_values = serialize_booking(db, booking)
    _set_status(db, booking, data.booking_status, actor, _user_role(actor), data.reason, data.metadata)
    log_audit(db, actor=actor, action="update_booking_status", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(db, booking), request=request)
    db.commit(); db.refresh(booking)

    if booking.customer and booking.customer.email:
        from app.utils.email_templates import booking_status_update_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        readable_status = data.booking_status.replace("_", " ").title()
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "new_status": readable_status, "reason": data.reason or "", "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Booking update - {booking.booking_code}",
            booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, data.booking_status, data.reason or "", login_url),
            booking.customer.email,
        )

    return serialize_booking_for_actor(db, booking, actor)


def _cancel_booking_core(
    db: Session,
    booking: "Booking",
    actor: Optional[User],
    request: Optional[Request],
    reason: Optional[str],
    source: str,
    role_label: str,
    audit_action: str,
    include_new_values: bool = True,
    before_commit=None,
    settle_reason: Optional[str] = None,
) -> "Booking":
    """Shared settlement sequence for cancel_booking / supplier_cancel_booking.

    Performs: status transition, cancellation bookkeeping fields, calendar
    seat release, payment settlement (100% refund of captured amount),
    affiliate/supplier/agent ledger reversal, customer counter adjustment,
    audit logging and commit. Role-specific notifications/emails are left to
    the caller. `before_commit`, if given, runs after the audit log is
    written but before the commit - this preserves cases where a caller's
    own (pre-existing) in-app notifications must land in the same
    transaction as the cancellation. `reason` is stored verbatim on the
    booking (matching each caller's prior, slightly different, None
    handling); `settle_reason` (defaults to `reason`) is what's passed to
    payment settlement, since one caller applies a fallback string there
    that it does NOT apply to the stored `cancellation_reason`.
    """
    old_values = serialize_booking(db, booking)
    _set_status(db, booking, "cancelled", actor, role_label, reason)
    booking.cancellation_reason = reason
    booking.cancellation_source = source
    booking.cancelled_at = utcnow()
    booking.cancelled_by = actor.id if actor else None
    if booking.calendar:
        booking.calendar.booked_seats = max(0, (booking.calendar.booked_seats or 0) - _booking_seat_count(booking))
    pending_before_cancel = money(booking.amount_pending)
    _settle_cancelled_booking_payments(db, booking, actor, request, settle_reason if settle_reason is not None else reason)
    try:
        from app.services.affiliate_tracking import reverse_conversion
        reverse_conversion(db, booking.id)
    except Exception:
        logger.warning("Affiliate conversion reversal failed for booking %s", booking.id, exc_info=True)
    try:
        from app.services.supplier_ledger import reverse_ledger_entry
        reverse_ledger_entry(db, booking.id)
    except Exception:
        logger.warning("Supplier ledger reversal failed for booking %s", booking.id, exc_info=True)
    try:
        from app.services.agent_ledger import reverse_ledger_entry as reverse_agent_ledger_entry
        reverse_agent_ledger_entry(db, booking.id)
    except Exception:
        logger.warning("Agent ledger reversal failed for booking %s", booking.id, exc_info=True)
    if booking.customer:
        booking.customer.upcoming_bookings = max(0, (booking.customer.upcoming_bookings or 0) - 1)
        booking.customer.total_amount_pending = max(
            money(0),
            money(booking.customer.total_amount_pending or 0) - pending_before_cancel,
        )
    new_values = serialize_booking(db, booking) if include_new_values else None
    log_audit(db, actor=actor, action=audit_action, entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=new_values, request=request)
    if before_commit is not None:
        before_commit()
    db.commit(); db.refresh(booking)
    return booking


def cancel_booking(db: Session, booking_id: int, data: BookingCancelRequest, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if booking.booking_status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    booking = _cancel_booking_core(
        db, booking, actor, request, data.reason, "admin", _user_role(actor),
        "cancel_booking", include_new_values=True,
        settle_reason=data.reason or "Cancelled by admin",
    )

    if booking.customer and booking.customer.email:
        from app.utils.email_templates import booking_cancelled_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings"
        _send_booking_email(
            db, "booking_cancelled",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "reason": data.reason or "Cancelled", "login_url": login_url, "button_text": "View bookings", "button_url": login_url},
            f"Booking cancelled - {booking.booking_code}",
            booking_cancelled_email(booking.customer.full_name, booking.booking_code, booking.tour_name, data.reason or "Cancelled", login_url),
            booking.customer.email,
        )

    if booking.supplier and booking.supplier.user and booking.supplier.user.email:
        from app.utils.email_templates import booking_cancelled_supplier_email
        portal_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_cancelled_supplier",
            {"supplier_name": booking.supplier.supplier_name, "booking_code": booking.booking_code,
             "tour_name": booking.tour_name, "reason": data.reason or "Cancelled", "portal_url": portal_url,
             "button_text": "View supplier portal", "button_url": portal_url},
            f"Booking cancelled - {booking.booking_code}",
            booking_cancelled_supplier_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, data.reason or "Cancelled", portal_url),
            booking.supplier.user.email,
        )

    if booking.agent and booking.agent.user_id:
        from app.services.notifications import enqueue_notification
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_cancelled", title="Booking cancelled", message=f"Booking {booking.booking_code} was cancelled: {data.reason or 'Cancelled'}", entity_type="booking", entity_id=booking.id)
    _email_agent_booking_status(db, booking, "cancelled", data.reason or "Cancelled")

    _email_admins_booking_event(db, "Booking cancelled", f"Booking {booking.booking_code} was cancelled. Reason: {data.reason or 'Cancelled'}", booking)

    return serialize_booking_for_actor(db, booking, actor)


OFFLINE_PAYMENT_HOLD_DAYS = 7


def expire_stale_pending_bookings(db: Session, older_than_minutes: int = 60) -> list[int]:
    """Release the calendar hold on bookings that never got paid.

    A booking that reaches pending_payment (or pending_credit_approval /
    pending_supplier_assignment, all of which sit "before payment" per
    BOOKING_STATUS_TRANSITIONS) and is then abandoned would otherwise hold
    its TourCalendar seats forever - nothing else in the codebase ever
    revisits an unpaid booking. This is meant to be run periodically (see
    the background loop registered in app.main) and can also be triggered
    on demand via POST /bookings/expire-stale.

    Returns the list of booking ids that were expired.
    """
    cutoff = utcnow() - timedelta(minutes=older_than_minutes)
    stale_statuses = ("pending_payment", "pending_credit_approval", "pending_supplier_assignment")
    # Agent credit / bank-transfer bookings wait on an offline step (admin
    # credit approval, a wire landing), so the short online-payment hold would
    # cancel them before that can happen. They get a much longer hold instead.
    offline_payment_statuses = ("credit_approval_pending", "bank_transfer_pending")
    offline_cutoff = utcnow() - timedelta(days=OFFLINE_PAYMENT_HOLD_DAYS)
    candidates = (
        db.query(Booking)
        .filter(Booking.booking_status.in_(stale_statuses))
        .filter(or_(
            and_(Booking.payment_status.notin_(offline_payment_statuses), Booking.created_at < cutoff),
            and_(Booking.payment_status.in_(offline_payment_statuses), Booking.created_at < offline_cutoff),
        ))
        .with_for_update()
        .all()
    )
    expired_ids: list[int] = []
    expired_codes: list[str] = []
    expired_bookings: list[Booking] = []
    for booking in candidates:
        reason = f"Automatically cancelled - no payment received in time"
        old_values = serialize_booking(db, booking)
        _set_status(db, booking, "cancelled", None, "system", reason)
        booking.cancellation_reason = reason
        booking.cancellation_source = "system_expiry"
        booking.cancelled_at = utcnow()
        if booking.calendar:
            booking.calendar.booked_seats = max(0, (booking.calendar.booked_seats or 0) - _booking_seat_count(booking))
        if booking.customer:
            booking.customer.upcoming_bookings = max(0, (booking.customer.upcoming_bookings or 0) - 1)
            booking.customer.total_amount_pending = max(money(0), money(booking.customer.total_amount_pending or 0) - money(booking.amount_pending))
        if booking.customer and booking.customer.user_id:
            from app.services.notifications import enqueue_notification
            enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_expired", title="Booking hold expired", message=f"Your booking {booking.booking_code} was automatically cancelled because payment wasn't completed in time.", entity_type="booking", entity_id=booking.id)
        if booking.agent and booking.agent.user_id:
            from app.services.notifications import enqueue_notification
            enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_expired", title="Booking hold expired", message=f"Booking {booking.booking_code} was automatically cancelled because payment wasn't completed in time.", entity_type="booking", entity_id=booking.id)
        # Same cleanup cancel_booking/supplier_decline_booking/
        # supplier_cancel_booking do - a "stale pending" booking can still
        # have a captured/authorized Payment row (e.g. a webhook landed
        # after the sweep's cutoff, or a partial payment didn't move the
        # booking out of pending_payment in time) and a supplier/affiliate
        # ledger entry already created for it; without this, that money and
        # those ledger rows are left orphaned instead of refunded/reversed.
        try:
            _settle_cancelled_booking_payments(db, booking, None, None, reason)
        except Exception:
            logger.warning("Payment settlement failed for expired booking %s", booking.id, exc_info=True)
        try:
            from app.services.affiliate_tracking import reverse_conversion
            reverse_conversion(db, booking.id)
        except Exception:
            logger.warning("Affiliate conversion reversal failed for expired booking %s", booking.id, exc_info=True)
        try:
            from app.services.supplier_ledger import reverse_ledger_entry
            reverse_ledger_entry(db, booking.id)
        except Exception:
            logger.warning("Supplier ledger reversal failed for expired booking %s", booking.id, exc_info=True)
        if booking.agent_id:
            try:
                from app.services.agent_ledger import reverse_ledger_entry as reverse_agent_ledger_entry
                reverse_agent_ledger_entry(db, booking.id)
            except Exception:
                logger.warning("Agent ledger reversal failed for booking %s", booking.id, exc_info=True)
        log_audit(
            db, actor=None, action="expire_stale_pending_booking", entity_type="booking",
            entity_id=booking.id, old_values=old_values, new_values=serialize_booking(db, booking),
            request=None,
        )
        expired_ids.append(booking.id)
        expired_codes.append(booking.booking_code or _booking_code(db, booking.id, booking.booking_source))
        expired_bookings.append(booking)

    if expired_ids:
        db.commit()
        logger.info("Expired %d stale pending booking(s): %s", len(expired_ids), expired_ids)
        from app.utils.email_templates import admin_booking_event_email
        from app.utils.notification_triggers import email_admins
        codes = ", ".join(expired_codes)
        detail = f"{len(expired_ids)} unpaid booking(s) were automatically cancelled after {older_than_minutes} minutes without payment."
        admin_url = f"{settings.FRONTEND_URL}/admin/bookings"
        email_admins(
            db, "admin_booking_event",
            {"event_title": "Bookings auto-cancelled", "detail": detail, "booking_code": codes, "tour_name": "",
             "admin_url": admin_url, "button_text": "View bookings", "button_url": admin_url},
            "Bookings auto-cancelled",
            admin_booking_event_email("Bookings auto-cancelled", detail, codes, "", admin_url),
        )
        from app.utils.email_templates import booking_status_update_email
        for booking in expired_bookings:
            reason = "Payment was not completed before the booking hold expired."
            if booking.customer and booking.customer.email:
                customer_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
                _send_booking_email(
                    db, "booking_status_update",
                    {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
                     "new_status": "Expired", "reason": reason, "login_url": customer_url,
                     "button_text": "View booking", "button_url": customer_url},
                    f"Booking expired - {booking.booking_code}",
                    booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, "expired", reason, customer_url),
                    booking.customer.email,
                )
            _email_agent_booking_status(db, booking, "booking expired", reason)
    return expired_ids


def assign_supplier(db: Session, booking_id: int, data: AssignSupplierRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    # "declined" is intentionally NOT in this blocking set: a declined booking
    # is reassignable to another supplier by design - BOOKING_STATUS_TRANSITIONS
    # explicitly allows declined -> pending_supplier_assignment. Only genuinely
    # terminal states block reassignment.
    if booking.booking_status in {"completed", "cancelled", "refunded"}:
        raise HTTPException(status_code=409, detail="A supplier cannot be assigned to a closed booking")
    old_values = serialize_booking(db, booking)
    booking.supplier_id = data.supplier_id
    booking.supplier_acceptance_status = "pending"
    _set_status(db, booking, "pending_supplier_acceptance", actor, "admin", data.reason)
    log_audit(db, actor=actor, action="assign_supplier", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(db, booking), request=request)
    db.commit(); db.refresh(booking)

    if _is_booking_fully_paid(booking) and booking.supplier and booking.supplier.user and booking.supplier.user.email:
        from app.utils.email_templates import supplier_booking_assigned_email
        customer_name = booking.customer.full_name if booking.customer else "Customer"
        portal_url = f"{settings.FRONTEND_URL}/supplier/bookings/{booking.id}"
        _send_booking_email(
            db, "supplier_booking_assigned",
            {"supplier_name": booking.supplier.supplier_name, "booking_code": booking.booking_code,
             "tour_name": booking.tour_name, "tour_date": booking.tour_date or "",
             "customer_name": customer_name, "adults": booking.adults_count,
             "currency": booking.currency, "total": booking.final_amount, "portal_url": portal_url,
             "button_text": "View booking", "button_url": portal_url},
            f"New booking assigned - {booking.booking_code}",
            supplier_booking_assigned_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, booking.tour_date or "", customer_name, booking.adults_count, booking.currency, money_str(supplier_booking_value(booking)), portal_url),
            booking.supplier.user.email,
        )

    return serialize_booking_for_actor(db, booking, actor)


def supplier_accept_booking(db: Session, booking_id: int, data: SupplierDecisionRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _start_supplier_decision(booking, "accepted"):
        return serialize_booking_for_actor(db, booking, actor)
    booking.supplier_acceptance_status = "accepted"
    _set_status(db, booking, "confirmed", actor, "supplier", data.reason or "Supplier accepted booking")

    from app.services.notifications import enqueue_notification, notify_admins
    from app.models.payments import Payment
    from app.schemas.payments import PaymentCapture
    from app.services.payments import capture_payment
    from app.schemas.invoices import InvoiceGenerateRequest
    from app.services.invoices import generate_invoice

    authorized_payments = list(db.query(Payment).filter(Payment.booking_id == booking.id, Payment.payment_status == "authorized").all())
    for payment in authorized_payments:
        amount = money(payment.authorized_amount) - money(payment.captured_amount)
        if amount > 0:
            capture_payment(db, payment.id, PaymentCapture(amount=amount, notes="Captured after supplier acceptance"), actor=actor, request=request)
            try:
                generate_invoice(db, InvoiceGenerateRequest(booking_id=booking.id, payment_id=payment.id), actor, request)
            except Exception as error:
                logger.warning("Invoice generation after supplier acceptance failed for booking %s and payment %s: %s", booking.id, payment.id, error)

    if booking.supplier_id:
        from app.models.supplier_ledger import SupplierLedger
        from app.services.supplier_ledger import create_ledger_entry
        existing_ledger = db.query(SupplierLedger).filter(SupplierLedger.booking_id == booking.id).first()
        if not existing_ledger:
            # Ledger figures come from the booking's locked snapshot, never
            # from today's slab/commission. A booking created before the
            # snapshot existed is locked now, from its own stored amounts.
            _lock_legacy_booking_financials(db, booking)
            breakdown = compute_booking_supplier_financials(db, booking)
            try:
                create_ledger_entry(db, booking=booking, supplier_id=booking.supplier_id, gross_amount=breakdown["gross_amount"], commission_amount=breakdown["commission_amount"])
            except Exception as error:
                logger.warning("Supplier ledger entry creation failed for booking %s: %s", booking.id, error)

    if booking.affiliate_ref_code:
        from app.services.settings import get_allow_agent_and_affiliate_same_booking

        if booking.booking_source == "agent" and not get_allow_agent_and_affiliate_same_booking(db):
            # Default business rule: an agent booking pays agent commission
            # ONLY -- it must not also pay affiliate commission on the same
            # booking (both are carved out of the same Tourvaa commission
            # pool, see _apply_commission_snapshot). Admin can opt back in
            # via allow_agent_and_affiliate_commission_same_booking.
            logger.info("Skipped affiliate conversion for agent booking %s (allow_agent_and_affiliate_commission_same_booking is off)", booking.id)
        else:
            try:
                from app.services.affiliate_tracking import record_conversion
                record_conversion(db, ref_code=booking.affiliate_ref_code, booking_id=booking.id, booking_amount=affiliate_eligible_amount(booking), currency=booking.currency or "USD")
            except Exception as error:
                logger.warning("Affiliate conversion recording failed for booking %s: %s", booking.id, error)

    notify_admins(db, notification_type="supplier_accepted_booking", title="Supplier accepted booking", message=f"Supplier accepted {booking.booking_code}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_confirmed", title="Booking confirmed", message=f"Booking {booking.booking_code} is confirmed", entity_type="booking", entity_id=booking.id)
    log_audit(db, actor=actor, action="supplier_accept_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(booking)

    # Payment-received emails (if any authorized holds were captured above)
    # are sent by payments.capture_payment itself, per capture - no separate
    # aggregate email needed here.
    if booking.customer and booking.customer.email:
        from app.utils.email_templates import booking_confirmed_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_confirmed",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "tour_date": booking.tour_date or "", "adults": booking.adults_count, "currency": booking.currency,
             "total": booking.final_amount, "login_url": login_url, "button_text": "View booking", "button_url": login_url},
            f"Your booking is confirmed - {booking.booking_code}",
            booking_confirmed_email(booking.customer.full_name, booking.booking_code, booking.tour_name, booking.tour_date or "", booking.adults_count, booking.currency, booking.final_amount, login_url),
            booking.customer.email,
        )

    if booking.supplier and booking.supplier.user and booking.supplier.user.email:
        from app.utils.email_templates import supplier_booking_confirmed_email
        portal_url = f"{settings.FRONTEND_URL}/supplier/bookings/{booking.id}"
        customer_name = booking.customer.full_name if booking.customer else "Customer"
        _send_booking_email(
            db, "supplier_booking_confirmed",
            {"supplier_name": booking.supplier.supplier_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "tour_date": booking.tour_date or "", "customer_name": customer_name, "adults": booking.adults_count, "currency": booking.currency, "total": booking.final_amount, "portal_url": portal_url, "button_text": "View booking", "button_url": portal_url},
            f"Booking confirmed - {booking.booking_code}",
            supplier_booking_confirmed_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, booking.tour_date or "", customer_name, booking.adults_count, booking.currency, money_str(supplier_booking_value(booking)), portal_url),
            booking.supplier.user.email,
        )

    # The agent is a booking party and must receive the final confirmation,
    # not an internal supplier-acceptance explanation.
    _email_agent_booking_status(db, booking, "confirmed", "Your booking is now confirmed.")

    _email_admins_booking_event(db, "Supplier accepted booking", f"Supplier accepted booking {booking.booking_code}.", booking)

    return serialize_booking_for_actor(db, booking, actor)


def supplier_set_due_date(db: Session, booking_id: int, data: SupplierDueDateUpdate, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if booking.supplier_acceptance_status != "accepted" or money(booking.amount_pending or 0) <= 0:
        raise HTTPException(status_code=400, detail="Due date can only be set on an accepted booking with an outstanding balance")

    due_date = _parse_dt(data.due_date)
    if due_date is None:
        raise HTTPException(status_code=400, detail="Invalid due_date")

    booking.payment_due_date = due_date
    log_audit(db, actor=actor, action="supplier_set_due_date", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking_for_actor(db, booking, actor)


def supplier_decline_booking(db: Session, booking_id: int, data: SupplierDecisionRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _start_supplier_decision(booking, "declined"):
        return serialize_booking_for_actor(db, booking, actor)
    pending_before_decline = money(booking.amount_pending)
    booking.supplier_acceptance_status = "declined"
    _set_status(db, booking, "declined", actor, "supplier", data.reason or "Supplier declined booking")
    if booking.calendar:
        booking.calendar.booked_seats = max(
            0,
            (booking.calendar.booked_seats or 0) - _booking_seat_count(booking),
        )

    from app.services.notifications import enqueue_notification, notify_admins
    _settle_cancelled_booking_payments(db, booking, actor, request, "Released after supplier decline")
    if booking.customer:
        booking.customer.upcoming_bookings = max(0, (booking.customer.upcoming_bookings or 0) - 1)
        booking.customer.total_amount_pending = max(
            money(0),
            money(booking.customer.total_amount_pending or 0) - pending_before_decline,
        )

    notify_admins(db, notification_type="supplier_declined_booking", title="Supplier declined booking", message=f"Supplier declined {booking.booking_code}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_declined", title="Booking declined", message=f"Booking {booking.booking_code} was declined by supplier", entity_type="booking", entity_id=booking.id)
    log_audit(db, actor=actor, action="supplier_decline_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(booking)

    if booking.customer and booking.customer.email:
        from app.utils.email_templates import booking_declined_email
        login_url = f"{settings.FRONTEND_URL}/tours"
        similar_tours = _similar_tours_for_email(db, booking.tour_id)
        _send_booking_email(
            db, "booking_declined",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "reason": data.reason or "Declined by supplier", "login_url": login_url,
             "button_text": "Browse tours", "button_url": login_url},
            f"Booking declined - {booking.booking_code}",
            booking_declined_email(booking.customer.full_name, booking.booking_code, booking.tour_name, data.reason or "Declined by supplier", login_url, similar_tours),
            booking.customer.email,
        )

    _email_admins_booking_event(db, "Supplier declined booking", f"Supplier declined booking {booking.booking_code}. Reason: {data.reason or 'Declined by supplier'}", booking)

    return serialize_booking_for_actor(db, booking, actor)


def supplier_start_booking(db: Session, booking_id: int, reason: str | None, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification, notify_admins
    from app.utils.email_templates import booking_status_update_email

    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _validate_supplier_lifecycle_transition(booking, "ongoing"):
        return serialize_booking_for_actor(db, booking, actor)

    old_values = serialize_booking(db, booking)
    transition_reason = reason or "Tour started by supplier"
    _set_status(db, booking, "ongoing", actor, "supplier", transition_reason)
    log_audit(db, actor=actor, action="supplier_start_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, request=request)
    notify_admins(db, notification_type="booking_ongoing", title="Tour started", message=f"Supplier started {booking.booking_code}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_ongoing", title="Your tour has started", message=f"Tour {booking.booking_code} is now ongoing", entity_type="booking", entity_id=booking.id)
    if booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_ongoing", title="Tour started", message=f"Booking {booking.booking_code} is now ongoing", entity_type="booking", entity_id=booking.id)
    db.commit(); db.refresh(booking)

    if booking.customer and booking.customer.email:
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "new_status": "Ongoing", "reason": transition_reason, "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Tour started - {booking.booking_code}",
            booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, "ongoing", transition_reason, login_url),
            booking.customer.email,
        )
    _email_agent_booking_status(db, booking, "ongoing", transition_reason)
    _email_admins_booking_event(db, "Tour started", f"Supplier started tour for booking {booking.booking_code}.", booking)
    return serialize_booking_for_actor(db, booking, actor)


def supplier_complete_booking(db: Session, booking_id: int, reason: str | None, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification, notify_admins
    from app.utils.email_templates import booking_status_update_email
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _validate_supplier_lifecycle_transition(booking, "completed"):
        return serialize_booking_for_actor(db, booking, actor)
    old_values = serialize_booking(db, booking)
    _set_status(db, booking, "completed", actor, "supplier", reason or "Tour completed by supplier")
    log_audit(db, actor=actor, action="supplier_complete_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, request=request)
    notify_admins(db, notification_type="booking_completed", title="Tour completed", message=f"Supplier marked {booking.booking_code} as completed", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_completed", title="Tour completed", message=f"Your tour {booking.booking_code} has been completed", entity_type="booking", entity_id=booking.id)
    if booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_completed", title="Tour completed", message=f"Booking {booking.booking_code} has been completed", entity_type="booking", entity_id=booking.id)
    if booking.customer:
        booking.customer.completed_bookings = (booking.customer.completed_bookings or 0) + 1
        booking.customer.upcoming_bookings = max(0, (booking.customer.upcoming_bookings or 0) - 1)
    db.commit(); db.refresh(booking)
    if booking.customer and booking.customer.email:
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "new_status": "Completed", "reason": reason or "Tour completed", "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Tour completed - {booking.booking_code}",
            booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, "completed", reason or "Tour completed", login_url),
            booking.customer.email,
        )
    _email_agent_booking_status(db, booking, "completed", reason or "Tour completed")
    _email_admins_booking_event(db, "Tour completed", f"Supplier marked booking {booking.booking_code} as completed.", booking)
    if booking.customer and booking.customer.email:
        from app.utils.email_templates import review_request_email
        review_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "review_request",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "login_url": review_url, "button_text": "Leave a review", "button_url": review_url},
            f"How was your tour? - {booking.booking_code}",
            review_request_email(booking.customer.full_name, booking.booking_code, booking.tour_name, review_url),
            booking.customer.email,
        )
    return serialize_booking_for_actor(db, booking, actor)


def check_booking_reminders(db: Session) -> list[int]:
    """Send one seven-day and one 24-hour reminder for confirmed upcoming tours.

    Communications are used as durable delivery markers, so restarts and the
    hourly scheduler cannot duplicate a reminder.
    """
    from app.services.notifications import enqueue_notification
    from app.utils.email_templates import booking_reminder_email

    today = utcnow().date()
    reminders_sent: list[int] = []
    bookings = db.query(Booking).filter(
        Booking.booking_status.in_({"confirmed", "ready_to_travel", "upcoming"}),
        Booking.tour_start_date.isnot(None),
    ).all()
    for booking in bookings:
        tour_date = as_aware_utc(booking.tour_start_date).date()
        days_until = (tour_date - today).days
        marker = "booking_reminder_7d" if days_until == 7 else "booking_reminder_24h" if days_until == 1 else None
        if not marker or not booking.customer:
            continue
        already_sent = db.query(BookingCommunication.id).filter(
            BookingCommunication.booking_id == booking.id,
            BookingCommunication.message_type == marker,
        ).first()
        if already_sent:
            continue
        label = "in 7 days" if days_until == 7 else "tomorrow"
        db.add(BookingCommunication(
            booking_id=booking.id, sender_type="system", message_type=marker,
            subject=f"Tour reminder - {booking.booking_code}",
            message=f"Your tour is {label} ({booking.tour_date}).", visibility="customer",
        ))
        if booking.customer.user_id:
            enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_reminder",
                title="Your tour is coming up", message=f"Your tour {booking.booking_code} is {label}.", entity_type="booking", entity_id=booking.id)
        if booking.customer.email:
            customer_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
            _send_booking_email(
                db, "booking_reminder",
                {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
                 "tour_date": booking.tour_date, "login_url": customer_url, "button_text": "View booking", "button_url": customer_url},
                f"Your tour is coming up - {booking.booking_code}",
                booking_reminder_email(booking.customer.full_name, booking.booking_code, booking.tour_name, booking.tour_date, customer_url),
                booking.customer.email,
            )
        _email_agent_booking_status(db, booking, "tour reminder", f"The tour is {label} ({booking.tour_date}).")
        reminders_sent.append(booking.id)
    if reminders_sent:
        db.commit()
    return reminders_sent


def supplier_cancel_booking(db: Session, booking_id: int, reason: str, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import notify_admins
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if booking.booking_status in {"cancelled", "completed", "refunded", "supplier_reassignment_required"}:
        raise HTTPException(status_code=400, detail=f"This booking cannot be withdrawn by the supplier (current status: '{booking.booking_status}')")

    # A supplier withdrawal is an internal fulfilment event, not a customer
    # or agent cancellation. Keep the payment, seats and traveller booking in
    # place so Tourvaa can assign another supplier; only Operations receives
    # the internal reason and reassignment status.
    old_values = serialize_booking(db, booking)
    booking.supplier_acceptance_status = "withdrawn"
    booking.cancellation_reason = reason
    booking.cancellation_source = "supplier_reassignment"
    _set_status(db, booking, "supplier_reassignment_required", actor, "supplier_reassignment", reason)
    log_audit(
        db, actor=actor, action="supplier_withdrew_booking", entity_type="booking", entity_id=booking.id,
        old_values=old_values, new_values=serialize_booking(db, booking), request=request,
    )
    notify_admins(
        db, notification_type="supplier_withdrew_booking", title="Supplier withdrawal requires reassignment",
        message=f"Supplier withdrew from booking {booking.booking_code}: {reason}", entity_type="booking", entity_id=booking.id,
    )
    db.commit(); db.refresh(booking)
    _email_admins_booking_event(db, "Supplier withdrawal requires reassignment", f"Supplier withdrew from booking {booking.booking_code}. Reason: {reason}", booking)
    if booking.supplier and booking.supplier.user and booking.supplier.user.email:
        from app.utils.email_templates import booking_status_update_email
        portal_url = f"{settings.FRONTEND_URL}/supplier/bookings"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.supplier.supplier_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "new_status": "Withdrawal request received", "reason": reason, "login_url": portal_url,
             "button_text": "View bookings", "button_url": portal_url},
            f"Supplier withdrawal received - {booking.booking_code}",
            booking_status_update_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, "withdrawal request received", reason, portal_url),
            booking.supplier.user.email,
        )
    return serialize_booking_for_actor(db, booking, actor)


def notify_paid_booking_ready_for_supplier(db: Session, booking: Booking) -> None:
    """Send operational assignment emails only after the booking is fully paid."""
    if not _is_booking_fully_paid(booking):
        return
    from app.services.notifications import enqueue_notification, notify_admins
    from app.utils.email_templates import new_booking_admin_email, supplier_booking_assigned_email
    from app.utils.notification_triggers import email_admins

    customer_name = booking.customer.full_name if booking.customer else "Customer"
    admin_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking.id}"
    supplier_name = booking.supplier.supplier_name if booking.supplier else "Unassigned"
    notify_admins(db, notification_type="paid_booking_ready", title="Paid booking ready for fulfilment", message=f"Booking {booking.booking_code} has been paid and is ready for fulfilment", entity_type="booking", entity_id=booking.id)
    email_admins(
        db, "new_booking_admin",
        {"booking_code": booking.booking_code, "tour_name": booking.tour_name, "tour_date": booking.tour_date or "", "customer_name": customer_name, "supplier_name": supplier_name, "adults": booking.adults_count, "currency": booking.currency, "total": booking.final_amount, "admin_url": admin_url, "button_text": "View booking", "button_url": admin_url},
        f"Paid booking ready - {booking.booking_code}",
        new_booking_admin_email(booking.booking_code, booking.tour_name, booking.tour_date or "", customer_name, supplier_name, booking.adults_count, booking.currency, booking.final_amount, admin_url),
    )
    if booking.booking_status != "pending_supplier_acceptance" or not (booking.supplier and booking.supplier.user and booking.supplier.user.email):
        return
    portal_url = f"{settings.FRONTEND_URL}/supplier/bookings/{booking.id}"
    enqueue_notification(db, user_id=booking.supplier.user_id, notification_type="supplier_booking_assigned", title="New paid booking assigned", message=f"Paid booking {booking.booking_code} is awaiting your acceptance", entity_type="booking", entity_id=booking.id)
    _send_booking_email(
        db, "supplier_booking_assigned",
        {"supplier_name": booking.supplier.supplier_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "tour_date": booking.tour_date or "", "customer_name": customer_name, "adults": booking.adults_count, "currency": booking.currency, "total": booking.final_amount, "portal_url": portal_url, "button_text": "View booking", "button_url": portal_url},
        f"New paid booking assigned - {booking.booking_code}",
        supplier_booking_assigned_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, booking.tour_date or "", customer_name, booking.adults_count, booking.currency, money_str(supplier_booking_value(booking)), portal_url),
        booking.supplier.user.email,
    )


def update_booking_travel_date(db: Session, booking_id: int, data: BookingTravelDateUpdate, actor: User, request: Request | None = None) -> dict:
    """Admin-only reschedule that keeps the tour calendar seat counts accurate."""
    booking = get_booking_by_id(db, booking_id, for_update=True)
    if _user_role(actor) != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can change a booking travel date")
    if booking.booking_status in {"cancelled", "completed", "declined", "refunded"}:
        raise HTTPException(status_code=400, detail=f"Cannot change the date of a {booking.booking_status} booking")
    try:
        requested_date = _parse_dt(data.tour_date)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid travel date") from exc
    if not requested_date:
        raise HTTPException(status_code=400, detail="Invalid travel date")

    old_values = {"tour_date": booking.tour_date, "tour_calendar_id": booking.tour_calendar_id}
    tour = db.query(Tour).filter(Tour.id == booking.tour_id).first() if booking.tour_id else None
    new_calendar = None
    if booking.tour_id:
        new_calendar = (
            db.query(TourCalendar)
            .filter(TourCalendar.tour_id == booking.tour_id, func.date(TourCalendar.tour_date) == requested_date.date())
            .with_for_update()
            .first()
        )
        if not new_calendar:
            raise HTTPException(status_code=400, detail="No tour calendar is available for the requested date")
        if new_calendar.status not in {"available", "active"}:
            raise HTTPException(status_code=400, detail="The requested tour date is not available")

    if new_calendar and new_calendar.id != booking.tour_calendar_id:
        seats = _booking_seat_count(booking)
        effective_capacity = _bookable_calendar_capacity(tour, new_calendar)
        if effective_capacity and (new_calendar.booked_seats or 0) + seats > effective_capacity:
            raise HTTPException(status_code=409, detail="Not enough seats are available on the requested tour date")
        old_calendar = (
            db.query(TourCalendar).filter(TourCalendar.id == booking.tour_calendar_id).with_for_update().first()
            if booking.tour_calendar_id else None
        )
        if old_calendar:
            old_calendar.booked_seats = max(0, (old_calendar.booked_seats or 0) - seats)
        new_calendar.booked_seats = (new_calendar.booked_seats or 0) + seats
        booking.tour_calendar_id = new_calendar.id

    booking.tour_date = (new_calendar.tour_date if new_calendar else requested_date).date().isoformat()
    booking.tour_start_date = (new_calendar.start_date or new_calendar.tour_date) if new_calendar else requested_date
    log_audit(
        db, actor=actor, action="admin_reschedule_booking", entity_type="booking", entity_id=booking.id,
        old_values=old_values, new_values={"tour_date": booking.tour_date, "tour_calendar_id": booking.tour_calendar_id, "reason": data.reason}, request=request,
    )
    from app.services.notifications import enqueue_notification
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_rescheduled", title="Travel date updated", message=f"Your booking {booking.booking_code} travel date has been updated to {booking.tour_date}.", entity_type="booking", entity_id=booking.id)
    if booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_rescheduled", title="Travel date updated", message=f"Booking {booking.booking_code} travel date has been updated to {booking.tour_date}.", entity_type="booking", entity_id=booking.id)
    db.commit(); db.refresh(booking)
    from app.utils.email_templates import booking_status_update_email
    if booking.customer and booking.customer.email:
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "new_status": "Travel date updated", "reason": data.reason, "login_url": login_url, "button_text": "View booking", "button_url": login_url},
            f"Travel date updated - {booking.booking_code}",
            booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, "travel date updated", data.reason, login_url),
            booking.customer.email,
        )
    _email_agent_booking_status(db, booking, "travel date updated", data.reason)
    if booking.supplier and booking.supplier.user and booking.supplier.user.email:
        portal_url = f"{settings.FRONTEND_URL}/supplier/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.supplier.supplier_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "new_status": "Travel date updated", "reason": data.reason, "login_url": portal_url, "button_text": "View booking", "button_url": portal_url},
            f"Travel date updated - {booking.booking_code}",
            booking_status_update_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, "travel date updated", data.reason, portal_url),
            booking.supplier.user.email,
        )
    return serialize_booking_for_actor(db, booking, actor)


def supplier_postpone_booking(
    db: Session,
    booking_id: int,
    reason: str,
    new_tour_date: str | None,
    actor: User,
    request: Request | None = None,
    new_tour_calendar_id: int | None = None,
) -> dict:
    from app.services.notifications import enqueue_notification, notify_admins
    from app.utils.email_templates import booking_status_update_email
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if booking.booking_status in ("cancelled", "completed", "declined"):
        raise HTTPException(status_code=400, detail=f"Cannot postpone a {booking.booking_status} booking")
    old_values = serialize_booking(db, booking)
    tour = db.query(Tour).filter(Tour.id == booking.tour_id).first() if booking.tour_id else None
    parsed_new_date = None
    if new_tour_date:
        try:
            parsed_new_date = _parse_dt(new_tour_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid new tour date") from exc

    new_calendar_query = db.query(TourCalendar)
    if new_tour_calendar_id:
        new_calendar_query = new_calendar_query.filter(TourCalendar.id == new_tour_calendar_id)
    elif parsed_new_date and booking.tour_id:
        new_calendar_query = new_calendar_query.filter(
            TourCalendar.tour_id == booking.tour_id,
            func.date(TourCalendar.tour_date) == parsed_new_date.date(),
        )
    else:
        new_calendar_query = None

    new_calendar = new_calendar_query.with_for_update().first() if new_calendar_query is not None else None
    if (new_tour_calendar_id or (parsed_new_date and booking.tour_calendar_id)) and not new_calendar:
        raise HTTPException(status_code=400, detail="No tour calendar is available for the requested date")
    if new_calendar:
        if booking.tour_id and new_calendar.tour_id != booking.tour_id:
            raise HTTPException(status_code=400, detail="New calendar date does not belong to this booking's tour")
        if new_calendar.status not in {"available", "active"}:
            raise HTTPException(status_code=400, detail="New calendar date is not available")
        seats = _booking_seat_count(booking)
        if new_calendar.id != booking.tour_calendar_id:
            effective_capacity = _bookable_calendar_capacity(tour, new_calendar)
            if effective_capacity and (new_calendar.booked_seats or 0) + seats > effective_capacity:
                raise HTTPException(status_code=409, detail="Not enough seats available on the new tour date")
            old_calendar = (
                db.query(TourCalendar)
                .filter(TourCalendar.id == booking.tour_calendar_id)
                .with_for_update()
                .first()
                if booking.tour_calendar_id
                else None
            )
            if old_calendar:
                old_calendar.booked_seats = max(0, (old_calendar.booked_seats or 0) - seats)
            new_calendar.booked_seats = (new_calendar.booked_seats or 0) + seats
            booking.tour_calendar_id = new_calendar.id
        booking.tour_date = new_calendar.tour_date.date().isoformat()
        booking.tour_start_date = new_calendar.start_date or new_calendar.tour_date
    elif parsed_new_date:
        booking.tour_date = parsed_new_date.date().isoformat()
        booking.tour_start_date = parsed_new_date
    _set_status(db, booking, "postponed", actor, "supplier", reason)
    log_audit(db, actor=actor, action="supplier_postpone_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, request=request)
    notify_admins(db, notification_type="booking_postponed", title="Booking postponed", message=f"Supplier postponed {booking.booking_code}: {reason}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_postponed", title="Booking postponed", message=f"Your booking {booking.booking_code} has been postponed. Reason: {reason}", entity_type="booking", entity_id=booking.id)
    if booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_postponed", title="Booking postponed", message=f"Booking {booking.booking_code} has been postponed by supplier", entity_type="booking", entity_id=booking.id)
    db.commit(); db.refresh(booking)
    if booking.customer and booking.customer.email:
        date_info = f" New date: {booking.tour_date}." if new_tour_date or new_tour_calendar_id else ""
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "new_status": "Postponed", "reason": reason + date_info, "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Booking postponed - {booking.booking_code}",
            booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, "postponed", reason + date_info, login_url),
            booking.customer.email,
        )

    _email_agent_booking_status(db, booking, "postponed", reason)
    _email_admins_booking_event(db, "Booking postponed", f"Supplier postponed booking {booking.booking_code}. Reason: {reason}", booking)
    return serialize_booking_for_actor(db, booking, actor)


def supplier_notify_parties(db: Session, booking_id: int, message: str, notify_customer: bool, notify_agent: bool, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification
    from app.utils.email_templates import booking_status_update_email
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    row = BookingCommunication(
        booking_id=booking.id, sender_user_id=actor.id, sender_type="supplier",
        message_type="supplier_update", subject=f"Update on booking {booking.booking_code}",
        message=message, visibility="customer",
    )
    db.add(row)
    log_audit(db, actor=actor, action="supplier_notify_parties", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(row)
    notified = []
    if notify_customer and booking.customer and booking.customer.email:
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        _send_booking_email(
            db, "booking_status_update",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "new_status": booking.booking_status.replace("_", " ").title(), "reason": message, "login_url": login_url,
             "button_text": "View booking", "button_url": login_url},
            f"Update on your booking - {booking.booking_code}",
            booking_status_update_email(booking.customer.full_name, booking.booking_code, booking.tour_name, booking.booking_status, message, login_url),
            booking.customer.email,
        )
        if booking.customer.user_id:
            enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_update", title=f"Update: {booking.booking_code}", message=message, entity_type="booking", entity_id=booking.id)
        notified.append("customer")
    if notify_agent and booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="booking_update", title=f"Supplier update: {booking.booking_code}", message=message, entity_type="booking", entity_id=booking.id)
        _email_agent_booking_status(db, booking, booking.booking_status, message)
        notified.append("agent")
    return {"message": "Notification sent", "notified": notified, "communication_id": row.id}


def get_status_history(db: Session, booking_id: int, actor: User | None = None) -> list[dict]:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    return [serialize_status_history(row) for row in db.query(BookingStatusHistory).filter(BookingStatusHistory.booking_id == booking_id).order_by(BookingStatusHistory.id.asc()).all()]


def get_upcoming_bookings(db: Session, actor: User | None = None) -> dict:
    return get_bookings(db, limit=20, booking_status="confirmed", sort_by="oldest", actor=actor)


def _communication_recipients(booking: Booking, visibility: str) -> list[tuple[str, str]]:
    """(label, email) pairs a booking communication should be emailed to, per its visibility."""
    recipients: list[tuple[str, str]] = []
    if visibility in ("customer", "all") and booking.customer and booking.customer.email:
        recipients.append(("customer", booking.customer.email))
    if visibility in ("supplier", "all") and booking.supplier and booking.supplier.user and booking.supplier.user.email:
        recipients.append(("supplier", booking.supplier.user.email))
    if visibility in ("agent", "all") and booking.agent and booking.agent.user and booking.agent.user.email:
        recipients.append(("agent", booking.agent.user.email))
    return recipients


def add_communication(db: Session, booking_id: int, data: BookingCommunicationCreate, actor: User, request: Request | None = None) -> dict:
    from html import escape
    from app.utils.mailer import try_send_email

    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    recipients = _communication_recipients(booking, data.visibility) if data.visibility != "internal" else []
    if data.visibility != "internal" and not recipients:
        raise HTTPException(status_code=400, detail=f"This booking has no {data.visibility} recipient to contact")
    row = BookingCommunication(booking_id=booking.id, sender_user_id=actor.id, sender_type=_user_role(actor), message_type=data.message_type, subject=data.subject, message=data.message, visibility=data.visibility)
    db.add(row)
    log_audit(db, actor=actor, action="create_booking_communication", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(row)

    # "internal" notes are admin-only and are never emailed to booking stakeholders.
    if data.visibility != "internal":
        subject = data.subject or f"Update on your booking {booking.booking_code or booking.id}"
        body = f"<p>{escape(data.message)}</p>"
        for _label, email in recipients:
            try_send_email(email, subject, body, template_key="booking_communication", entity_type="booking_communication", entity_id=row.id)

    return serialize_communication(row)


def get_customer_bookings(db: Session, customer_id: int, page: int = 1, limit: int = 20, booking_status: str = "", payment_status: str = "") -> dict:
    return get_bookings(db, page=page, limit=limit, customer_id=customer_id, booking_status=booking_status, payment_status=payment_status)


def get_payment_link(db: Session, booking_id: int, actor: User | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    return {"booking_id": booking.id, "booking_code": booking.booking_code, "amount_pending": money_str(booking.amount_pending), "payment_link": f"/payments?booking_id={booking.id}"}


def export_bookings(db: Session, actor: User | None = None) -> list[dict]:
    return get_bookings(db, page=1, limit=1000, actor=actor)["items"]


def add_communication_reply(db: Session, communication_id: int, message: str, actor: User, request: Request | None = None) -> dict:
    from app.models.bookings import MessageReply
    row = db.query(BookingCommunication).filter(BookingCommunication.id == communication_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Communication not found")
    booking = get_booking_by_id(db, row.booking_id)
    _ensure_booking_access(booking, actor)
    reply = MessageReply(communication_id=row.id, sender_user_id=actor.id, sender_type=_user_role(actor), message=message)
    db.add(reply)
    log_audit(db, actor=actor, action="reply_booking_communication", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(reply)
    return {"id": reply.id, "communication_id": reply.communication_id, "sender_user_id": reply.sender_user_id, "sender_type": reply.sender_type, "message": reply.message, "created_at": reply.created_at}





def notify_overdue_agent_balances(db: Session) -> list[int]:
    """Flag agent 'Reserve Now' (pay_later) bookings whose balance is past its due date.

    Deliberately does NOT cancel: these bookings already hold a deposit, and
    cancelling one triggers refund/forfeit rules that are an admin decision
    (use cancel_booking). Instead the agent gets a reminder and admins get an
    alert - once per booking (deduped on the Notification row).

    Returns the ids of bookings flagged this run.
    """
    from app.models.notifications import Notification
    from app.services.notifications import enqueue_notification, notify_admins

    closed = ("cancelled", "completed", "declined", "refunded", "cancellation_requested", "draft")
    candidates = (
        db.query(Booking)
        .filter(Booking.booking_source == "agent", Booking.agent_payment_method == "pay_later")
        .filter(~Booking.booking_status.in_(closed))
        .filter(Booking.amount_pending > 0)
        .all()
    )
    now = utcnow()
    flagged: list[int] = []
    for booking in candidates:
        due = _balance_due_date(db, booking)
        if due is None:
            continue
        # _balance_due_date returns a date for the agent buffer window and a
        # datetime elsewhere; a date is overdue once that whole day has passed.
        if not isinstance(due, datetime):
            due = datetime.combine(due, datetime.max.time())
        if due.tzinfo is None:
            due = due.replace(tzinfo=now.tzinfo)
        if due >= now:
            continue
        already = db.query(Notification.id).filter(
            Notification.notification_type == "balance_overdue",
            Notification.entity_type == "booking",
            Notification.entity_id == booking.id,
        ).first()
        if already:
            continue
        code = booking.booking_code or _booking_code(db, booking.id, booking.booking_source)
        if booking.agent and booking.agent.user_id:
            enqueue_notification(
                db, user_id=booking.agent.user_id, notification_type="balance_overdue",
                title="Balance payment overdue",
                message=f"The balance for booking {code} was due on {due:%d %b %Y}. Please pay now to keep the booking.",
                entity_type="booking", entity_id=booking.id,
            )
        notify_admins(
            db, notification_type="balance_overdue", title="Agent balance overdue",
            message=f"Booking {code} has an unpaid balance past its {due:%d %b %Y} due date.",
            entity_type="booking", entity_id=booking.id,
        )
        flagged.append(booking.id)
    if flagged:
        db.commit()
        logger.info("Flagged %d booking(s) with overdue agent balances: %s", len(flagged), flagged)
    return flagged
