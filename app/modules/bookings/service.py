from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    BookingCancelRequest,
    BookingCreate,
    BookingStatusUpdate,
    BookingUpdate,
)
from app.modules.customers.models import Customer
from app.modules.users.models import User


def _booking_code(booking_id: int) -> str:
    return f"TVA-BKG-{booking_id:05d}"


def _paginate(items: list, page: int, limit: int) -> dict:
    total = len(items)
    start = (page - 1) * limit
    page_items = items[start : start + limit]
    return {
        "items": page_items,
        "data": page_items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)),
    }


def serialize_booking(booking: Booking) -> dict:
    return {
        "id": booking.id,
        "booking_code": booking.booking_code or _booking_code(booking.id),
        "customer_id": booking.customer_id,
        "tour_id": booking.tour_id,
        "supplier_id": booking.supplier_id,
        "agent_id": booking.agent_id,
        "affiliate_id": booking.affiliate_id,
        "tour_name": booking.tour_name,
        "tour_date": booking.tour_date,
        "country": booking.country,
        "supplier_name": booking.supplier_name,
        "no_of_adults": booking.no_of_adults,
        "no_of_children": booking.no_of_children,
        "no_of_infants": booking.no_of_infants,
        "total_cost": float(booking.total_cost or 0),
        "amount_paid": float(booking.amount_paid or 0),
        "amount_pending": float(booking.amount_pending or 0),
        "booking_status": booking.booking_status,
        "payment_status": booking.payment_status,
        "notes": booking.notes,
        "cancellation_reason": booking.cancellation_reason,
        "cancelled_at": booking.cancelled_at,
        "created_at": booking.created_at,
        "updated_at": booking.updated_at,
    }


def get_booking_by_id(db: Session, booking_id: int) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def get_bookings(
    db: Session,
    page: int = 1,
    limit: int = 20,
    search: str = "",
    customer_id: Optional[int] = None,
    booking_status: str = "",
    payment_status: str = "",
    start_date: str = "",
    end_date: str = "",
    sort_by: str = "newest",
) -> dict:
    query = db.query(Booking)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                Booking.booking_code.ilike(pattern),
                Booking.tour_name.ilike(pattern),
                Booking.country.ilike(pattern),
                Booking.supplier_name.ilike(pattern),
            )
        )

    if customer_id:
        query = query.filter(Booking.customer_id == customer_id)

    if booking_status:
        query = query.filter(Booking.booking_status == booking_status.strip().lower())

    if payment_status:
        query = query.filter(Booking.payment_status == payment_status.strip().lower())

    if start_date:
        query = query.filter(Booking.created_at >= start_date)

    if end_date:
        query = query.filter(Booking.created_at <= f"{end_date} 23:59:59")

    if sort_by == "oldest":
        query = query.order_by(Booking.id.asc())
    else:
        query = query.order_by(Booking.id.desc())

    total = query.count()
    bookings = query.offset((page - 1) * limit).limit(limit).all()
    items = [serialize_booking(b) for b in bookings]

    return {
        "items": items,
        "data": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)),
    }


def get_booking_detail(
    db: Session,
    booking_id: int,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    booking = get_booking_by_id(db, booking_id)
    log_audit(
        db,
        actor=actor,
        action="view_booking",
        entity_type="booking",
        entity_id=booking.id,
        request=request,
    )
    db.commit()
    return serialize_booking(booking)


def create_booking(
    db: Session,
    data: BookingCreate,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    booking = Booking(
        customer_id=data.customer_id,
        tour_id=data.tour_id,
        supplier_id=data.supplier_id,
        agent_id=data.agent_id,
        affiliate_id=data.affiliate_id,
        created_by=actor.id if actor else None,
        tour_name=data.tour_name.strip(),
        tour_date=data.tour_date.strip(),
        country=data.country.strip(),
        supplier_name=data.supplier_name.strip(),
        no_of_adults=data.no_of_adults,
        no_of_children=data.no_of_children,
        no_of_infants=data.no_of_infants,
        total_cost=data.total_cost,
        amount_paid=0,
        amount_pending=data.total_cost,
        booking_status="upcoming",
        payment_status="pending",
        notes=data.notes,
    )
    db.add(booking)
    db.flush()
    booking.booking_code = _booking_code(booking.id)

    # Update customer counters
    customer.total_bookings = (customer.total_bookings or 0) + 1
    customer.upcoming_bookings = (customer.upcoming_bookings or 0) + 1
    customer.total_amount_pending = float(customer.total_amount_pending or 0) + float(data.total_cost)

    log_audit(
        db,
        actor=actor,
        action="create_booking",
        entity_type="booking",
        entity_id=booking.id,
        new_values=serialize_booking(booking),
        request=request,
    )
    db.commit()
    db.refresh(booking)
    return serialize_booking(booking)


def update_booking(
    db: Session,
    booking_id: int,
    data: BookingUpdate,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    booking = get_booking_by_id(db, booking_id)
    old_values = serialize_booking(booking)

    for field in ["tour_name", "tour_date", "country", "supplier_name", "notes"]:
        value = getattr(data, field)
        if value is not None:
            setattr(booking, field, value.strip() if isinstance(value, str) else value)

    for field in ["no_of_adults", "no_of_children", "no_of_infants", "supplier_id", "agent_id", "affiliate_id"]:
        value = getattr(data, field)
        if value is not None:
            setattr(booking, field, value)

    if data.total_cost is not None:
        booking.total_cost = data.total_cost
        booking.amount_pending = max(0, float(data.total_cost) - float(booking.amount_paid or 0))

    log_audit(
        db,
        actor=actor,
        action="update_booking",
        entity_type="booking",
        entity_id=booking.id,
        old_values=old_values,
        new_values=serialize_booking(booking),
        request=request,
    )
    db.commit()
    db.refresh(booking)
    return serialize_booking(booking)


def update_booking_status(
    db: Session,
    booking_id: int,
    data: BookingStatusUpdate,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    booking = get_booking_by_id(db, booking_id)
    old_values = serialize_booking(booking)
    old_status = booking.booking_status
    booking.booking_status = data.booking_status

    # Sync customer counters when status changes
    customer = booking.customer
    if customer and old_status != data.booking_status:
        if old_status == "upcoming":
            customer.upcoming_bookings = max(0, (customer.upcoming_bookings or 0) - 1)
        elif old_status == "completed":
            customer.completed_bookings = max(0, (customer.completed_bookings or 0) - 1)
        elif old_status == "cancelled":
            customer.cancelled_bookings = max(0, (customer.cancelled_bookings or 0) - 1)

        if data.booking_status == "upcoming":
            customer.upcoming_bookings = (customer.upcoming_bookings or 0) + 1
        elif data.booking_status == "completed":
            customer.completed_bookings = (customer.completed_bookings or 0) + 1
        elif data.booking_status == "cancelled":
            customer.cancelled_bookings = (customer.cancelled_bookings or 0) + 1

    log_audit(
        db,
        actor=actor,
        action="update_booking_status",
        entity_type="booking",
        entity_id=booking.id,
        old_values=old_values,
        new_values=serialize_booking(booking),
        request=request,
    )
    db.commit()
    db.refresh(booking)
    return serialize_booking(booking)


def cancel_booking(
    db: Session,
    booking_id: int,
    data: BookingCancelRequest,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    booking = get_booking_by_id(db, booking_id)
    if booking.booking_status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")

    old_values = serialize_booking(booking)
    old_status = booking.booking_status
    booking.booking_status = "cancelled"
    booking.cancellation_reason = data.reason
    booking.cancelled_at = datetime.utcnow()
    booking.cancelled_by = actor.id if actor else None

    customer = booking.customer
    if customer:
        if old_status == "upcoming":
            customer.upcoming_bookings = max(0, (customer.upcoming_bookings or 0) - 1)
        elif old_status == "completed":
            customer.completed_bookings = max(0, (customer.completed_bookings or 0) - 1)
        customer.cancelled_bookings = (customer.cancelled_bookings or 0) + 1

    log_audit(
        db,
        actor=actor,
        action="cancel_booking",
        entity_type="booking",
        entity_id=booking.id,
        old_values=old_values,
        new_values=serialize_booking(booking),
        request=request,
    )
    db.commit()
    db.refresh(booking)
    return serialize_booking(booking)


def get_customer_bookings(
    db: Session,
    customer_id: int,
    page: int = 1,
    limit: int = 20,
    booking_status: str = "",
    payment_status: str = "",
) -> dict:
    query = db.query(Booking).filter(Booking.customer_id == customer_id)

    if booking_status:
        query = query.filter(Booking.booking_status == booking_status.strip().lower())
    if payment_status:
        query = query.filter(Booking.payment_status == payment_status.strip().lower())

    query = query.order_by(Booking.id.desc())
    total = query.count()
    items = [serialize_booking(b) for b in query.offset((page - 1) * limit).limit(limit).all()]

    return {
        "items": items,
        "data": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)),
    }
