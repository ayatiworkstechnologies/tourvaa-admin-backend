import logging
from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.services.audit import log_audit
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
    BookingCancelRequest,
    BookingCommunicationCreate,
    BookingCreate,
    BookingStatusUpdate,
    BookingUpdate,
    SupplierDecisionRequest,
)
from app.models.cms import City, Country, Tour
from app.utils.money import money, money_str, utcnow
from app.models.customers import Customer
from app.models.agents import Agent
from app.models.suppliers import Supplier
from app.models.tours import TourAccommodationExtra, TourCalendar, TourDiscount, TourExtension, TourOptionalActivity, TourPricing, TourUnavailableDate
from app.models.users import User

logger = logging.getLogger(__name__)


def _send_booking_email(db, key: str, values: dict, fallback_subject: str, fallback_html: str, to_email: str):
    from app.utils.email_templates import render_database_email
    from app.utils.mailer import try_send_email
    try:
        subject, html = render_database_email(db, key, values, fallback_subject, fallback_html)
        try_send_email(to_email, subject, html)
    except Exception as exc:
        logger.warning("Booking email %s to %s failed: %s", key, to_email, exc)


def _booking_code(booking_id: int) -> str:
    return f"TVA-BKG-{booking_id:06d}"


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _mask_passport(value: str | None) -> str | None:
    if not value:
        return value
    return "*" * max(len(value) - 4, 0) + value[-4:]


def _user_role(user: User | None) -> str:
    if not user or not user.role:
        return "admin"
    slug = user.role.slug or ""
    if "supplier" in slug:
        return "supplier"
    if "agent" in slug:
        return "agent"
    if "customer" in slug:
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
    "confirmed": {"ready_to_travel", "ongoing", "completed", "postponed", "cancellation_requested", "cancelled"},
    "ready_to_travel": {"ongoing", "completed", "postponed", "cancellation_requested", "cancelled"},
    "upcoming": {"confirmed", "ready_to_travel", "ongoing", "completed", "postponed", "cancellation_requested", "cancelled"},
    "ongoing": {"completed", "postponed", "cancellation_requested", "cancelled"},
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


def serialize_booking(booking: Booking, detail: bool = False) -> dict:
    data = {
        "id": booking.id,
        "booking_code": booking.booking_code or _booking_code(booking.id),
        "customer_id": booking.customer_id,
        "customer_name": booking.customer.full_name if booking.customer else None,
        "customer_email": booking.customer.email if booking.customer else None,
        "tour_id": booking.tour_id,
        "tour_calendar_id": booking.tour_calendar_id,
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
        "supplier_name": booking.supplier_name,
        "no_of_adults": booking.no_of_adults,
        "no_of_children": booking.no_of_children,
        "no_of_infants": booking.no_of_infants,
        "adults_count": booking.adults_count,
        "children_count": booking.children_count,
        "total_travellers": booking.total_travellers,
        "currency": booking.currency,
        "total_cost": money_str(booking.total_cost),
        "base_amount": money_str(booking.base_amount),
        "optional_activity_amount": money_str(booking.optional_activity_amount),
        "accommodation_amount": money_str(booking.accommodation_amount),
        "extension_amount": money_str(booking.extension_amount),
        "discount_amount": money_str(booking.discount_amount),
        "tax_amount": money_str(booking.tax_amount),
        "surcharge_amount": money_str(booking.surcharge_amount),
        "final_amount": money_str(booking.final_amount),
        "agent_net_price": money_str(booking.agent_net_price),
        "agent_markup": money_str(booking.agent_markup),
        "customer_selling_price": money_str(booking.customer_selling_price),
        "amount_paid": money_str(booking.amount_paid),
        "amount_pending": money_str(booking.amount_pending),
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
        "cancelled_at": booking.cancelled_at,
        "created_at": booking.created_at,
        "updated_at": booking.updated_at,
    }
    if detail:
        data.update({
            "customer": {"id": booking.customer.id, "name": booking.customer.full_name, "email": booking.customer.email} if booking.customer else None,
            "supplier": {"id": booking.supplier.id, "supplier_name": booking.supplier.supplier_name} if booking.supplier else None,
            "travellers": [serialize_traveller(t) for t in booking.travellers],
            "optional_activities": [serialize_activity(a) for a in booking.optional_activities],
            "accommodations": [serialize_accommodation(a) for a in booking.accommodations],
            "extensions": [serialize_extension(e) for e in booking.extensions],
            "payments": [],
            "status_history": [serialize_status_history(h) for h in booking.status_history],
            "communications": [serialize_communication(c) for c in booking.communications],
            "price_breakdown": {
                "base_amount": money_str(booking.base_amount),
                "optional_activity_amount": _money_total(booking.optional_activities),
                "accommodation_amount": _money_total(booking.accommodations),
                "extension_amount": _money_total(booking.extensions),
                "discount_amount": money_str(booking.discount_amount),
                "tax_amount": money_str(booking.tax_amount),
                "surcharge_amount": money_str(booking.surcharge_amount),
                "final_amount": money_str(booking.final_amount),
                "agent_net_price": money_str(booking.agent_net_price),
                "agent_markup": money_str(booking.agent_markup),
                "customer_selling_price": money_str(booking.customer_selling_price),
            },
            "payment_summary": {"status": booking.payment_status, "paid": money_str(booking.amount_paid), "pending": money_str(booking.amount_pending)},
            "invoice_summary": None,
        })
    return data


def serialize_traveller(t: BookingTraveller) -> dict:
    return {"id": t.id, "traveller_type": t.traveller_type, "first_name": t.first_name, "last_name": t.last_name, "full_name": t.full_name, "age": t.age, "gender": t.gender, "nationality": t.nationality, "passport_number": _mask_passport(t.passport_number), "email": t.email, "phone": t.phone, "is_primary_contact": bool(t.is_primary_contact), "special_requirements": t.special_requirements}


def serialize_activity(a: BookingOptionalActivity) -> dict:
    return {"id": a.id, "tour_optional_activity_id": a.tour_optional_activity_id, "activity_name_snapshot": a.activity_name_snapshot, "quantity": a.quantity, "unit_price": money_str(a.unit_price), "total_price": money_str(a.total_price)}


def serialize_accommodation(a: BookingAccommodation) -> dict:
    return {"id": a.id, "tour_accommodation_extra_id": a.tour_accommodation_extra_id, "accommodation_name_snapshot": a.accommodation_name_snapshot, "quantity": a.quantity, "price_type": a.price_type, "unit_price": money_str(a.unit_price), "total_price": money_str(a.total_price)}


def serialize_extension(e: BookingExtension) -> dict:
    return {"id": e.id, "tour_extension_id": e.tour_extension_id, "extension_tour_id": e.extension_tour_id, "extension_name_snapshot": e.extension_name_snapshot, "quantity": e.quantity, "unit_price": money_str(e.unit_price), "total_price": money_str(e.total_price)}


def serialize_communication(c: BookingCommunication) -> dict:
    return {"id": c.id, "booking_id": c.booking_id, "sender_user_id": c.sender_user_id, "sender_type": c.sender_type, "message_type": c.message_type, "subject": c.subject, "message": c.message, "visibility": c.visibility, "created_at": c.created_at}


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


def _resolve_discount(db: Session, promo_code: str | None, tour, subtotal, consume: bool = False):
    """Look up and validate a promo code against tour_discounts. Raises 400 if the
    code doesn't exist or doesn't apply; returns 0 if no code was supplied."""
    if not promo_code or not promo_code.strip():
        return money(0)
    code = promo_code.strip()
    discount = db.query(TourDiscount).filter(TourDiscount.discount_code == code, TourDiscount.status == "active").first()
    if not discount:
        raise HTTPException(status_code=400, detail="Invalid or inactive promo code")
    now = utcnow()
    if discount.start_date and now < discount.start_date:
        raise HTTPException(status_code=400, detail="Promo code is not yet active")
    if discount.end_date and now > discount.end_date:
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
    return money(amount)


def _price_booking(db: Session, data: BookingCreate, lock_calendar: bool = False, consume_discount: bool = False):
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
    if calendar:
        if calendar.tour_id != data.tour_id:
            raise HTTPException(status_code=400, detail="Calendar date does not belong to tour")
        if calendar.status not in {"available", "active"}:
            raise HTTPException(status_code=400, detail="Selected tour date is not available")
        if calendar.available_seats and calendar.booked_seats + seat_travellers > calendar.available_seats:
            raise HTTPException(status_code=409, detail="Not enough seats available")
    if data.tour_id and data.tour_start_date:
        start = _parse_dt(data.tour_start_date)
        blocked = db.query(TourUnavailableDate).filter(TourUnavailableDate.tour_id == data.tour_id, func.date(TourUnavailableDate.unavailable_date) == start.date()).first()
        if blocked:
            raise HTTPException(status_code=400, detail="Selected date is unavailable")

    slab = None
    if data.tour_id:
        slab = db.query(TourPricing).filter(TourPricing.tour_id == data.tour_id, TourPricing.status == "active", TourPricing.passenger_from <= seat_travellers, TourPricing.passenger_to >= seat_travellers).first()
    currency = slab.currency if slab else (tour.currency if tour else data.currency)
    adult_unit = money(slab.adult_price if slab else (tour.price_start_per_person if tour else 0))
    child_unit = money(slab.child_price if slab else 0)
    base_amount = money(adult_unit * adults + child_unit * children)

    activity_rows = []
    activity_total = money(0)
    for item in data.optional_activities:
        row = db.query(TourOptionalActivity).filter(TourOptionalActivity.id == item.id, TourOptionalActivity.status == "active").first() if item.id else None
        if not row or (data.tour_id and row.tour_id != data.tour_id):
            raise HTTPException(status_code=400, detail="Invalid optional activity")
        unit = money(row.price_per_person)
        total = money(unit * item.quantity)
        activity_total += total
        activity_rows.append((row, item.quantity, unit, total))

    accommodation_rows = []
    accommodation_total = money(0)
    for item in data.accommodations:
        row = db.query(TourAccommodationExtra).filter(TourAccommodationExtra.id == item.id, TourAccommodationExtra.status == "active").first() if item.id else None
        if not row or (data.tour_id and row.tour_id != data.tour_id):
            raise HTTPException(status_code=400, detail="Invalid accommodation extra")
        unit = money(row.extra_price)
        qty = seat_travellers if row.price_type == "per_person" else item.quantity
        total = money(unit * qty)
        accommodation_total += total
        accommodation_rows.append((row, qty, unit, total))

    extension_rows = []
    extension_total = money(0)
    for item in data.extensions:
        row = db.query(TourExtension).filter(TourExtension.id == item.id, TourExtension.status == "active").first() if item.id else None
        if not row or (data.tour_id and row.tour_id != data.tour_id):
            raise HTTPException(status_code=400, detail="Invalid tour extension")
        unit = money(row.extra_price)
        total = money(unit * item.quantity)
        extension_total += total
        extension_rows.append((row, item.quantity, unit, total))

    subtotal = money(base_amount + activity_total + accommodation_total + extension_total)
    discount = _resolve_discount(db, data.promo_code, tour, subtotal, consume=consume_discount)
    tax = money(0)
    surcharge = money(0)
    final = money(base_amount + activity_total + accommodation_total + extension_total - discount + tax + surcharge)
    if final < 0:
        raise HTTPException(status_code=400, detail="Final amount cannot be negative")
    return tour, calendar, adults, children, total_travellers, currency, base_amount, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activity_rows, accommodation_rows, extension_rows


def calculate_booking_price(db: Session, data: BookingCreate) -> dict:
    tour, calendar, adults, children, total_travellers, currency, base, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activities, accommodations, extensions = _price_booking(db, data)
    agent_markup = money(data.agent_markup if data.booking_source == "agent" else 0)
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
        "discount_amount": money_str(discount),
        "tax_amount": money_str(tax),
        "surcharge_amount": money_str(surcharge),
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
    role = _user_role(actor)
    if role == "supplier":
        query = query.join(Booking.supplier).filter_by(user_id=actor.id)
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
    items = [serialize_booking(b) for b in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit)), "status_counts": status_counts}


def get_booking_detail(db: Session, booking_id: int, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    log_audit(db, actor=actor, action="view_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit()
    return serialize_booking(booking, detail=True)


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
        if row.traveller_type == "child" and not 2 <= row.age <= 11:
            raise HTTPException(status_code=400, detail="Child traveller age must be between 2 and 11")


def create_booking(db: Session, data: BookingCreate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if data.booking_source == "customer" and not data.customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required for customer bookings")
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
    tour, calendar, adults, children, total_travellers, currency, base, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activities, accommodations, extensions = _price_booking(db, data, lock_calendar=True, consume_discount=True)
    _validate_customer_travellers(data, adults, children)
    country = db.query(Country).filter(Country.id == (data.country_id or (tour.country_id if tour else None))).first() if (data.country_id or tour) else None
    city = db.query(City).filter(City.id == (data.city_id or (tour.city_id if tour else None))).first() if (data.city_id or tour) else None
    supplier = tour.supplier if tour and tour.supplier else None
    supplier_id = data.supplier_id or (supplier.id if supplier else None)
    agent_net_price = final if data.booking_source == "agent" else money(0)
    agent_markup = money(data.agent_markup if data.booking_source == "agent" else 0)
    customer_selling_price = money(final + agent_markup) if data.booking_source == "agent" else final
    payment_status = "pending"
    booking_status = "pending_payment"
    if data.booking_source == "agent" and data.agent_payment_method in {"credit", "pay_later"}:
        payment_status = "credit_approval_pending"
        booking_status = "pending_credit_approval"
    elif data.booking_source == "agent" and data.agent_payment_method == "bank_transfer":
        payment_status = "bank_transfer_pending"
    booking = Booking(
        customer_id=data.customer_id, tour_id=data.tour_id, tour_calendar_id=data.tour_calendar_id, supplier_id=supplier_id, agent_id=data.agent_id, affiliate_id=data.affiliate_id, created_by=actor.id if actor else None, booked_by_user_id=actor.id if actor else None, booking_source=data.booking_source, country_id=data.country_id or (tour.country_id if tour else None), city_id=data.city_id or (tour.city_id if tour else None),
        tour_name=(data.tour_name or (tour.title if tour else "")).strip(), tour_date=(data.tour_date or (calendar.tour_date.date().isoformat() if calendar and calendar.tour_date else "")).strip(), country=(data.country or (country.country_name if country else "")).strip(), supplier_name=(data.supplier_name or (supplier.supplier_name if supplier else "")).strip(), tour_start_date=_parse_dt(data.tour_start_date) or (calendar.tour_date if calendar else None), tour_end_date=_parse_dt(data.tour_end_date),
        no_of_adults=adults, no_of_children=children, no_of_infants=data.no_of_infants, adults_count=adults, children_count=children, total_travellers=total_travellers, currency=currency,
        total_cost=customer_selling_price, base_amount=base, optional_activity_amount=activity_total, accommodation_amount=accommodation_total, extension_amount=extension_total, discount_amount=discount, promo_code=data.promo_code, tax_amount=tax, surcharge_amount=surcharge, final_amount=customer_selling_price, agent_net_price=agent_net_price, agent_markup=agent_markup, customer_selling_price=customer_selling_price, amount_paid=money(0), amount_pending=customer_selling_price,
        booking_status=booking_status, supplier_acceptance_status="pending" if supplier_id else "not_assigned", payment_status=payment_status, payment_type=data.payment_type, agent_payment_method=data.agent_payment_method if data.booking_source == "agent" else None, agent_reference=data.agent_reference if data.booking_source == "agent" else None, notes=data.notes, customer_notes=data.customer_notes, admin_notes=data.admin_notes,
    )
    db.add(booking)
    db.flush()
    booking.booking_code = _booking_code(booking.id)
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
    log_audit(db, actor=actor, action="create_booking", entity_type="booking", entity_id=booking.id, new_values=serialize_booking(booking), request=request)
    from app.services.notifications import enqueue_notification, notify_admins
    notify_admins(db, notification_type="new_booking", title="New booking created", message=f"Booking {booking.booking_code} was created", entity_type="booking", entity_id=booking.id)
    if customer.user_id:
        enqueue_notification(db, user_id=customer.user_id, notification_type="booking_created", title="Booking created", message=f"Your booking {booking.booking_code} was created", entity_type="booking", entity_id=booking.id)
    if booking.supplier and booking.supplier.user_id:
        enqueue_notification(db, user_id=booking.supplier.user_id, notification_type="supplier_booking_assigned", title="New booking assigned", message=f"Booking {booking.booking_code} is awaiting your acceptance", entity_type="booking", entity_id=booking.id)
    db.commit()
    db.refresh(booking)

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
    )

    if booking.supplier_id and booking.supplier and booking.supplier.user and booking.supplier.user.email:
        from app.utils.email_templates import supplier_booking_assigned_email
        portal_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking.id}"
        _send_booking_email(
            db, "supplier_booking_assigned",
            {"supplier_name": booking.supplier.supplier_name, "booking_code": booking.booking_code,
             "tour_name": booking.tour_name, "tour_date": booking.tour_date or "",
             "customer_name": customer.full_name, "adults": booking.adults_count,
             "currency": booking.currency, "total": booking.final_amount, "portal_url": portal_url,
             "button_text": "View booking", "button_url": portal_url},
            f"New booking assigned - {booking.booking_code}",
            supplier_booking_assigned_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, booking.tour_date or "", customer.full_name, booking.adults_count, booking.currency, booking.final_amount, portal_url),
            booking.supplier.user.email,
        )

    return serialize_booking(booking, detail=True)


def update_booking(db: Session, booking_id: int, data: BookingUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    if _user_role(actor) == "agent":
        agent_editable = {"notes", "customer_notes"}
        restricted = set(data.model_fields_set) - agent_editable
        if restricted:
            raise HTTPException(status_code=403, detail="Agents may only update booking notes")
    old_values = serialize_booking(booking)
    for field in ["tour_name", "tour_date", "country", "supplier_name", "notes", "customer_notes", "admin_notes"]:
        value = getattr(data, field)
        if value is not None:
            setattr(booking, field, value.strip() if isinstance(value, str) else value)
    for field in ["no_of_adults", "no_of_children", "no_of_infants", "supplier_id", "agent_id", "affiliate_id"]:
        value = getattr(data, field)
        if value is not None:
            setattr(booking, field, value)
    if data.total_cost is not None:
        new_total = money(data.total_cost)
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
    log_audit(db, actor=actor, action="update_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


def update_booking_status(db: Session, booking_id: int, data: BookingStatusUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    if _user_role(actor) == "agent":
        raise HTTPException(status_code=403, detail="Agents cannot directly change booking status")
    _validate_booking_status_transition(booking.booking_status, data.booking_status)
    old_values = serialize_booking(booking)
    _set_status(db, booking, data.booking_status, actor, _user_role(actor), data.reason, data.metadata)
    log_audit(db, actor=actor, action="update_booking_status", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
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

    return serialize_booking(booking, detail=True)


def cancel_booking(db: Session, booking_id: int, data: BookingCancelRequest, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if booking.booking_status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    old_values = serialize_booking(booking)
    _set_status(db, booking, "cancelled", actor, _user_role(actor), data.reason)
    booking.cancellation_reason = data.reason
    booking.cancelled_at = utcnow()
    booking.cancelled_by = actor.id if actor else None
    if booking.calendar:
        booking.calendar.booked_seats = max(0, (booking.calendar.booked_seats or 0) - _booking_seat_count(booking))
    pending_before_cancel = money(booking.amount_pending)
    _settle_cancelled_booking_payments(db, booking, actor, request, data.reason or "Cancelled by admin")
    if booking.customer:
        booking.customer.upcoming_bookings = max(0, (booking.customer.upcoming_bookings or 0) - 1)
        booking.customer.total_amount_pending = max(
            money(0),
            money(booking.customer.total_amount_pending or 0) - pending_before_cancel,
        )
    log_audit(db, actor=actor, action="cancel_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)

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

    return serialize_booking(booking, detail=True)


def assign_supplier(db: Session, booking_id: int, data: AssignSupplierRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if booking.booking_status in {"completed", "cancelled", "declined", "refunded"}:
        raise HTTPException(status_code=409, detail="A supplier cannot be assigned to a closed booking")
    old_values = serialize_booking(booking)
    booking.supplier_id = data.supplier_id
    booking.supplier_acceptance_status = "pending"
    _set_status(db, booking, "pending_supplier_acceptance", actor, "admin", data.reason)
    log_audit(db, actor=actor, action="assign_supplier", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)

    if booking.supplier and booking.supplier.user and booking.supplier.user.email:
        from app.utils.email_templates import supplier_booking_assigned_email
        customer_name = booking.customer.full_name if booking.customer else "Customer"
        portal_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking.id}"
        _send_booking_email(
            db, "supplier_booking_assigned",
            {"supplier_name": booking.supplier.supplier_name, "booking_code": booking.booking_code,
             "tour_name": booking.tour_name, "tour_date": booking.tour_date or "",
             "customer_name": customer_name, "adults": booking.adults_count,
             "currency": booking.currency, "total": booking.final_amount, "portal_url": portal_url,
             "button_text": "View booking", "button_url": portal_url},
            f"New booking assigned - {booking.booking_code}",
            supplier_booking_assigned_email(booking.supplier.supplier_name, booking.booking_code, booking.tour_name, booking.tour_date or "", customer_name, booking.adults_count, booking.currency, booking.final_amount, portal_url),
            booking.supplier.user.email,
        )

    return serialize_booking(booking, detail=True)


def supplier_accept_booking(db: Session, booking_id: int, data: SupplierDecisionRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _start_supplier_decision(booking, "accepted"):
        return serialize_booking(booking, detail=True)
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
            markup_type = (booking.supplier.markup_type or "").strip().lower() if booking.supplier else ""
            commission_percentage = money(booking.supplier.markup_value) if booking.supplier and markup_type == "percentage" else money(0)
            try:
                create_ledger_entry(db, booking=booking, supplier_id=booking.supplier_id, gross_amount=money(booking.final_amount or booking.total_cost or 0), commission_percentage=commission_percentage)
            except Exception as error:
                logger.warning("Supplier ledger entry creation failed for booking %s: %s", booking.id, error)

    notify_admins(db, notification_type="supplier_accepted_booking", title="Supplier accepted booking", message=f"Supplier accepted {booking.booking_code}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_confirmed", title="Booking confirmed", message=f"Booking {booking.booking_code} is confirmed", entity_type="booking", entity_id=booking.id)
    log_audit(db, actor=actor, action="supplier_accept_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(booking)

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
        if authorized_payments:
            from app.utils.email_templates import payment_received_email
            total_captured = sum(money(p.captured_amount) for p in authorized_payments)
            _send_booking_email(
                db, "payment_received",
                {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
                 "currency": booking.currency, "amount": total_captured, "login_url": login_url,
                 "button_text": "View booking", "button_url": login_url},
                f"Payment received - {booking.booking_code}",
                payment_received_email(booking.customer.full_name, booking.booking_code, booking.tour_name, booking.currency, total_captured, login_url),
                booking.customer.email,
            )

    return serialize_booking(booking, detail=True)


def supplier_decline_booking(db: Session, booking_id: int, data: SupplierDecisionRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _start_supplier_decision(booking, "declined"):
        return serialize_booking(booking, detail=True)
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
        _send_booking_email(
            db, "booking_declined",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "reason": data.reason or "Declined by supplier", "login_url": login_url,
             "button_text": "Browse tours", "button_url": login_url},
            f"Booking declined - {booking.booking_code}",
            booking_declined_email(booking.customer.full_name, booking.booking_code, booking.tour_name, data.reason or "Declined by supplier", login_url),
            booking.customer.email,
        )

    return serialize_booking(booking, detail=True)


def supplier_start_booking(db: Session, booking_id: int, reason: str | None, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification, notify_admins
    from app.utils.email_templates import booking_status_update_email

    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _validate_supplier_lifecycle_transition(booking, "ongoing"):
        return serialize_booking(booking, detail=True)

    old_values = serialize_booking(booking)
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
    return serialize_booking(booking, detail=True)


def supplier_complete_booking(db: Session, booking_id: int, reason: str | None, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification, notify_admins
    from app.utils.email_templates import booking_status_update_email
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if not _validate_supplier_lifecycle_transition(booking, "completed"):
        return serialize_booking(booking, detail=True)
    old_values = serialize_booking(booking)
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
    return serialize_booking(booking, detail=True)


def supplier_cancel_booking(db: Session, booking_id: int, reason: str, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification, notify_admins
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    if booking.booking_status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    if booking.booking_status == "completed":
        raise HTTPException(status_code=400, detail="Completed bookings cannot be cancelled")
    old_values = serialize_booking(booking)
    _set_status(db, booking, "cancelled", actor, "supplier", reason)
    booking.cancellation_reason = reason
    booking.cancelled_at = utcnow()
    booking.cancelled_by = actor.id if actor else None
    pending_before_cancel = money(booking.amount_pending)
    if booking.calendar:
        booking.calendar.booked_seats = max(0, (booking.calendar.booked_seats or 0) - _booking_seat_count(booking))
    _settle_cancelled_booking_payments(db, booking, actor, request, reason)
    if booking.customer:
        booking.customer.upcoming_bookings = max(0, (booking.customer.upcoming_bookings or 0) - 1)
        booking.customer.total_amount_pending = max(
            money(0),
            money(booking.customer.total_amount_pending or 0) - pending_before_cancel,
        )
    log_audit(db, actor=actor, action="supplier_cancel_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, request=request)
    notify_admins(db, notification_type="supplier_cancelled_booking", title="Supplier cancelled booking", message=f"Supplier cancelled {booking.booking_code}: {reason}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_cancelled", title="Booking cancelled", message=f"Your booking {booking.booking_code} was cancelled by supplier", entity_type="booking", entity_id=booking.id)
    db.commit(); db.refresh(booking)
    if booking.customer and booking.customer.email:
        from app.utils.email_templates import booking_cancelled_email
        login_url = f"{settings.FRONTEND_URL}/customer/bookings"
        _send_booking_email(
            db, "booking_cancelled",
            {"name": booking.customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
             "reason": reason, "login_url": login_url, "button_text": "View bookings", "button_url": login_url},
            f"Booking cancelled - {booking.booking_code}",
            booking_cancelled_email(booking.customer.full_name, booking.booking_code, booking.tour_name, reason, login_url),
            booking.customer.email,
        )
    return serialize_booking(booking, detail=True)


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
    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    if booking.booking_status in ("cancelled", "completed", "declined"):
        raise HTTPException(status_code=400, detail=f"Cannot postpone a {booking.booking_status} booking")
    old_values = serialize_booking(booking)
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
            if new_calendar.available_seats and (new_calendar.booked_seats or 0) + seats > new_calendar.available_seats:
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
    return serialize_booking(booking, detail=True)


def supplier_notify_parties(db: Session, booking_id: int, message: str, notify_customer: bool, notify_agent: bool, actor: User, request: Request | None = None) -> dict:
    from app.services.notifications import enqueue_notification
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
        notified.append("agent")
    return {"message": "Notification sent", "notified": notified, "communication_id": row.id}


def get_status_history(db: Session, booking_id: int, actor: User | None = None) -> list[dict]:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    return [serialize_status_history(row) for row in db.query(BookingStatusHistory).filter(BookingStatusHistory.booking_id == booking_id).order_by(BookingStatusHistory.id.asc()).all()]


def get_upcoming_bookings(db: Session, actor: User | None = None) -> dict:
    return get_bookings(db, limit=20, booking_status="confirmed", sort_by="oldest", actor=actor)


def add_communication(db: Session, booking_id: int, data: BookingCommunicationCreate, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    row = BookingCommunication(booking_id=booking.id, sender_user_id=actor.id, sender_type=_user_role(actor), message_type=data.message_type, subject=data.subject, message=data.message, visibility=data.visibility)
    db.add(row)
    log_audit(db, actor=actor, action="create_booking_communication", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(row)
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



