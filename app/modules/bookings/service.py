import logging
from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.bookings.models import (
    Booking,
    BookingAccommodation,
    BookingCommunication,
    BookingExtension,
    BookingOptionalActivity,
    BookingStatusHistory,
    BookingTraveller,
)
from app.modules.bookings.schemas import (
    AssignSupplierRequest,
    BookingCancelRequest,
    BookingCommunicationCreate,
    BookingCreate,
    BookingStatusUpdate,
    BookingUpdate,
    SupplierDecisionRequest,
)
from app.modules.cms.models import City, Country, Tour
from app.modules.common.money import money, money_str, utcnow
from app.modules.customers.models import Customer
from app.modules.tours.models import TourAccommodationExtra, TourCalendar, TourExtension, TourOptionalActivity, TourPricing, TourUnavailableDate
from app.modules.users.models import User

logger = logging.getLogger(__name__)


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
        "amount_paid": money_str(booking.amount_paid),
        "amount_pending": money_str(booking.amount_pending),
        "booking_status": booking.booking_status,
        "supplier_acceptance_status": booking.supplier_acceptance_status,
        "payment_status": booking.payment_status,
        "payment_type": booking.payment_type,
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
            "customer": {"id": booking.customer.id, "name": booking.customer.name, "email": booking.customer.email} if booking.customer else None,
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


def get_booking_by_id(db: Session, booking_id: int) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _price_booking(db: Session, data: BookingCreate):
    adults = data.adults_count if data.adults_count is not None else data.no_of_adults
    children = data.children_count if data.children_count is not None else data.no_of_children
    total_travellers = adults + children
    if total_travellers <= 0:
        raise HTTPException(status_code=400, detail="At least one traveller is required")

    tour = db.query(Tour).filter(Tour.id == data.tour_id).first() if data.tour_id else None
    calendar = db.query(TourCalendar).filter(TourCalendar.id == data.tour_calendar_id).first() if data.tour_calendar_id else None
    if data.tour_id and not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    if tour and tour.status != "published":
        raise HTTPException(status_code=400, detail="Tour must be published before booking")
    if calendar:
        if calendar.tour_id != data.tour_id:
            raise HTTPException(status_code=400, detail="Calendar date does not belong to tour")
        if calendar.status not in {"available", "active"}:
            raise HTTPException(status_code=400, detail="Selected tour date is not available")
        if calendar.available_seats and calendar.booked_seats + total_travellers > calendar.available_seats:
            raise HTTPException(status_code=409, detail="Not enough seats available")
    if data.tour_id and data.tour_start_date:
        start = _parse_dt(data.tour_start_date)
        blocked = db.query(TourUnavailableDate).filter(TourUnavailableDate.tour_id == data.tour_id, func.date(TourUnavailableDate.unavailable_date) == start.date()).first()
        if blocked:
            raise HTTPException(status_code=400, detail="Selected date is unavailable")

    slab = None
    if data.tour_id:
        slab = db.query(TourPricing).filter(TourPricing.tour_id == data.tour_id, TourPricing.status == "active", TourPricing.passenger_from <= total_travellers, TourPricing.passenger_to >= total_travellers).first()
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
        qty = total_travellers if row.price_type == "per_person" else item.quantity
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

    discount = money(0)
    tax = money(0)
    surcharge = money(0)
    final = money(base_amount + activity_total + accommodation_total + extension_total - discount + tax + surcharge)
    if final < 0:
        raise HTTPException(status_code=400, detail="Final amount cannot be negative")
    return tour, calendar, adults, children, total_travellers, currency, base_amount, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activity_rows, accommodation_rows, extension_rows


def get_bookings(db: Session, page: int = 1, limit: int = 20, search: str = "", customer_id: Optional[int] = None, booking_status: str = "", payment_status: str = "", supplier_acceptance_status: str = "", country_id: Optional[int] = None, supplier_id: Optional[int] = None, agent_id: Optional[int] = None, tour_id: Optional[int] = None, start_date: str = "", end_date: str = "", sort_by: str = "newest", actor: Optional[User] = None) -> dict:
    query = db.query(Booking)
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
    if booking_status:
        query = query.filter(Booking.booking_status == booking_status.strip().lower())
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
    query = query.order_by(Booking.id.asc() if sort_by == "oldest" else Booking.id.desc())
    total = query.count()
    items = [serialize_booking(b) for b in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def get_booking_detail(db: Session, booking_id: int, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    log_audit(db, actor=actor, action="view_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit()
    return serialize_booking(booking, detail=True)


def create_booking(db: Session, data: BookingCreate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if data.booking_source == "customer" and not data.customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required for customer bookings")
    if data.booking_source == "agent" and not data.agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required for agent bookings")
    tour, calendar, adults, children, total_travellers, currency, base, activity_total, accommodation_total, extension_total, discount, tax, surcharge, final, activities, accommodations, extensions = _price_booking(db, data)
    country = db.query(Country).filter(Country.id == (data.country_id or (tour.country_id if tour else None))).first() if (data.country_id or tour) else None
    city = db.query(City).filter(City.id == (data.city_id or (tour.city_id if tour else None))).first() if (data.city_id or tour) else None
    supplier = tour.supplier if tour and tour.supplier else None
    supplier_id = data.supplier_id or (supplier.id if supplier else None)
    booking = Booking(
        customer_id=data.customer_id, tour_id=data.tour_id, tour_calendar_id=data.tour_calendar_id, supplier_id=supplier_id, agent_id=data.agent_id, affiliate_id=data.affiliate_id, created_by=actor.id if actor else None, booked_by_user_id=actor.id if actor else None, booking_source=data.booking_source, country_id=data.country_id or (tour.country_id if tour else None), city_id=data.city_id or (tour.city_id if tour else None),
        tour_name=(data.tour_name or (tour.title if tour else "")).strip(), tour_date=(data.tour_date or (calendar.tour_date.date().isoformat() if calendar and calendar.tour_date else "")).strip(), country=(data.country or (country.country_name if country else "")).strip(), supplier_name=(data.supplier_name or (supplier.supplier_name if supplier else "")).strip(), tour_start_date=_parse_dt(data.tour_start_date) or (calendar.tour_date if calendar else None), tour_end_date=_parse_dt(data.tour_end_date),
        no_of_adults=adults, no_of_children=children, no_of_infants=data.no_of_infants, adults_count=adults, children_count=children, total_travellers=total_travellers, currency=currency,
        total_cost=final, base_amount=base, optional_activity_amount=activity_total, accommodation_amount=accommodation_total, extension_amount=extension_total, discount_amount=discount, promo_code=data.promo_code, tax_amount=tax, surcharge_amount=surcharge, final_amount=final, amount_paid=money(0), amount_pending=final,
        booking_status="pending_payment", supplier_acceptance_status="pending" if supplier_id else "not_assigned", payment_status="unpaid", payment_type=data.payment_type, notes=data.notes, customer_notes=data.customer_notes, admin_notes=data.admin_notes,
    )
    db.add(booking)
    db.flush()
    booking.booking_code = _booking_code(booking.id)
    if calendar:
        calendar.booked_seats += total_travellers
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
    customer.total_amount_pending = money(customer.total_amount_pending or 0) + final
    log_audit(db, actor=actor, action="create_booking", entity_type="booking", entity_id=booking.id, new_values=serialize_booking(booking), request=request)
    from app.modules.notifications.service import enqueue_notification, notify_admins
    notify_admins(db, notification_type="new_booking", title="New booking created", message=f"Booking {booking.booking_code} was created", entity_type="booking", entity_id=booking.id)
    if customer.user_id:
        enqueue_notification(db, user_id=customer.user_id, notification_type="booking_created", title="Booking created", message=f"Your booking {booking.booking_code} was created", entity_type="booking", entity_id=booking.id)
    if booking.supplier and booking.supplier.user_id:
        enqueue_notification(db, user_id=booking.supplier.user_id, notification_type="supplier_booking_assigned", title="New booking assigned", message=f"Booking {booking.booking_code} is awaiting your acceptance", entity_type="booking", entity_id=booking.id)
    db.commit()
    db.refresh(booking)
    return serialize_booking(booking, detail=True)


def update_booking(db: Session, booking_id: int, data: BookingUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
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
        booking.total_cost = money(data.total_cost)
        booking.final_amount = money(data.total_cost)
        booking.amount_pending = max(money(0), money(data.total_cost) - money(booking.amount_paid))
    log_audit(db, actor=actor, action="update_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


def update_booking_status(db: Session, booking_id: int, data: BookingStatusUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    old_values = serialize_booking(booking)
    _set_status(db, booking, data.booking_status, actor, _user_role(actor), data.reason, data.metadata)
    log_audit(db, actor=actor, action="update_booking_status", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


def cancel_booking(db: Session, booking_id: int, data: BookingCancelRequest, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    if booking.booking_status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    old_values = serialize_booking(booking)
    _set_status(db, booking, "cancelled", actor, _user_role(actor), data.reason)
    booking.cancellation_reason = data.reason
    booking.cancelled_at = utcnow()
    booking.cancelled_by = actor.id if actor else None
    if booking.calendar:
        booking.calendar.booked_seats = max(0, (booking.calendar.booked_seats or 0) - (booking.total_travellers or 0))
    log_audit(db, actor=actor, action="cancel_booking", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


def assign_supplier(db: Session, booking_id: int, data: AssignSupplierRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    old_values = serialize_booking(booking)
    booking.supplier_id = data.supplier_id
    booking.supplier_acceptance_status = "pending"
    _set_status(db, booking, "pending_supplier_acceptance", actor, "admin", data.reason)
    log_audit(db, actor=actor, action="assign_supplier", entity_type="booking", entity_id=booking.id, old_values=old_values, new_values=serialize_booking(booking), request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


def supplier_accept_booking(db: Session, booking_id: int, data: SupplierDecisionRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    booking.supplier_acceptance_status = "accepted"
    _set_status(db, booking, "confirmed", actor, "supplier", data.reason or "Supplier accepted booking")

    from app.modules.notifications.service import enqueue_notification, notify_admins
    from app.modules.payments.models import Payment
    from app.modules.payments.schemas import PaymentCapture
    from app.modules.payments.service import capture_payment
    from app.modules.invoices.schemas import InvoiceGenerateRequest
    from app.modules.invoices.service import generate_invoice

    authorized_payments = list(db.query(Payment).filter(Payment.booking_id == booking.id, Payment.payment_status == "authorized").all())
    for payment in authorized_payments:
        amount = money(payment.authorized_amount) - money(payment.captured_amount)
        if amount > 0:
            capture_payment(db, payment.id, PaymentCapture(amount=amount, notes="Captured after supplier acceptance"), actor=actor, request=request)
            try:
                generate_invoice(db, InvoiceGenerateRequest(booking_id=booking.id, payment_id=payment.id), actor, request)
            except Exception as error:
                logger.warning("Invoice generation after supplier acceptance failed for booking %s and payment %s: %s", booking.id, payment.id, error)

    notify_admins(db, notification_type="supplier_accepted_booking", title="Supplier accepted booking", message=f"Supplier accepted {booking.booking_code}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_confirmed", title="Booking confirmed", message=f"Booking {booking.booking_code} is confirmed", entity_type="booking", entity_id=booking.id)
    log_audit(db, actor=actor, action="supplier_accept_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


def supplier_decline_booking(db: Session, booking_id: int, data: SupplierDecisionRequest, actor: User, request: Request | None = None) -> dict:
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    booking.supplier_acceptance_status = "declined"
    _set_status(db, booking, "declined", actor, "supplier", data.reason or "Supplier declined booking")

    from app.modules.notifications.service import enqueue_notification, notify_admins
    from app.modules.payments.models import Payment
    from app.modules.payments.schemas import PaymentVoid, RefundRequest
    from app.modules.payments.service import process_refund, void_payment

    payments = list(db.query(Payment).filter(Payment.booking_id == booking.id).all())
    for payment in payments:
        if payment.payment_status == "authorized" and money(payment.captured_amount) <= 0:
            void_payment(db, payment.id, PaymentVoid(reason="Released after supplier decline"), actor=actor, request=request)
        elif money(payment.captured_amount) > money(payment.refunded_amount):
            amount = money(payment.captured_amount) - money(payment.refunded_amount)
            process_refund(db, payment.id, RefundRequest(amount=amount, reason="Refund after supplier decline"), actor=actor, request=request)

    notify_admins(db, notification_type="supplier_declined_booking", title="Supplier declined booking", message=f"Supplier declined {booking.booking_code}", entity_type="booking", entity_id=booking.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="booking_declined", title="Booking declined", message=f"Booking {booking.booking_code} was declined by supplier", entity_type="booking", entity_id=booking.id)
    log_audit(db, actor=actor, action="supplier_decline_booking", entity_type="booking", entity_id=booking.id, request=request)
    db.commit(); db.refresh(booking)
    return serialize_booking(booking, detail=True)


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
    from app.modules.bookings.models import MessageReply
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


