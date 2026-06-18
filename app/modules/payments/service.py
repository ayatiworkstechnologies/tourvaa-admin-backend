from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.bookings.models import Booking
from app.modules.customers.models import Customer
from app.modules.payments.models import Payment
from app.modules.payments.schemas import (
    PaymentCreate,
    PaymentStatusUpdate,
    PaymentUpdate,
    RefundRequest,
)
from app.modules.users.models import User


def _payment_code(payment_id: int) -> str:
    return f"PAY-{payment_id:05d}"


def serialize_payment(payment: Payment) -> dict:
    return {
        "id": payment.id,
        "payment_code": payment.payment_code or _payment_code(payment.id),
        "booking_id": payment.booking_id,
        "customer_id": payment.customer_id,
        "payment_method": payment.payment_method,
        "payment_type": payment.payment_type,
        "total_amount": float(payment.total_amount or 0),
        "paid_amount": float(payment.paid_amount or 0),
        "pending_amount": float(payment.pending_amount or 0),
        "gst_amount": float(payment.gst_amount or 0),
        "refunded_amount": float(payment.refunded_amount or 0),
        "payment_status": payment.payment_status,
        "transaction_id": payment.transaction_id,
        "payment_date": payment.payment_date,
        "notes": payment.notes,
        "failure_reason": payment.failure_reason,
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
    }


def _derive_payment_status(paid: float, total: float) -> str:
    if paid <= 0:
        return "pending"
    if paid >= total:
        return "paid"
    return "partial"


def _sync_booking_payment_fields(db: Session, booking: Booking) -> None:
    payments = db.query(Payment).filter(Payment.booking_id == booking.id).all()
    total_paid = sum(float(p.paid_amount or 0) for p in payments if p.payment_status != "refunded")
    total_refunded = sum(float(p.refunded_amount or 0) for p in payments)
    net_paid = max(0.0, total_paid - total_refunded)
    booking.amount_paid = net_paid
    booking.amount_pending = max(0.0, float(booking.total_cost or 0) - net_paid)
    booking.payment_status = _derive_payment_status(net_paid, float(booking.total_cost or 0))


def _sync_customer_payment_fields(db: Session, customer: Customer) -> None:
    from sqlalchemy import func as sqlfunc

    paid_result = (
        db.query(sqlfunc.coalesce(sqlfunc.sum(Payment.paid_amount), 0))
        .filter(Payment.customer_id == customer.id, Payment.payment_status != "refunded")
        .scalar()
    )
    pending_result = (
        db.query(sqlfunc.coalesce(sqlfunc.sum(Booking.amount_pending), 0))
        .filter(Booking.customer_id == customer.id)
        .scalar()
    )
    customer.total_amount_paid = float(paid_result or 0)
    customer.total_amount_pending = float(pending_result or 0)


def get_payment_by_id(db: Session, payment_id: int) -> Payment:
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


def get_payments(
    db: Session,
    page: int = 1,
    limit: int = 20,
    search: str = "",
    customer_id: Optional[int] = None,
    booking_id: Optional[int] = None,
    payment_status: str = "",
    payment_method: str = "",
    start_date: str = "",
    end_date: str = "",
) -> dict:
    query = db.query(Payment)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                Payment.payment_code.ilike(pattern),
                Payment.transaction_id.ilike(pattern),
            )
        )

    if customer_id:
        query = query.filter(Payment.customer_id == customer_id)

    if booking_id:
        query = query.filter(Payment.booking_id == booking_id)

    if payment_status:
        query = query.filter(Payment.payment_status == payment_status.strip().lower())

    if payment_method:
        query = query.filter(Payment.payment_method == payment_method.strip().lower())

    if start_date:
        query = query.filter(Payment.created_at >= start_date)

    if end_date:
        query = query.filter(Payment.created_at <= f"{end_date} 23:59:59")

    query = query.order_by(Payment.id.desc())
    total = query.count()
    items = [serialize_payment(p) for p in query.offset((page - 1) * limit).limit(limit).all()]

    return {
        "items": items,
        "data": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)),
    }


def get_payment_detail(
    db: Session,
    payment_id: int,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    payment = get_payment_by_id(db, payment_id)
    log_audit(
        db,
        actor=actor,
        action="view_payment",
        entity_type="payment",
        entity_id=payment.id,
        request=request,
    )
    db.commit()
    return serialize_payment(payment)


def create_payment(
    db: Session,
    data: PaymentCreate,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.customer_id != data.customer_id:
        raise HTTPException(status_code=400, detail="Customer does not match booking")

    paid = float(data.paid_amount)
    total = float(data.total_amount)
    pending = max(0.0, total - paid)

    payment = Payment(
        booking_id=data.booking_id,
        customer_id=data.customer_id,
        created_by=actor.id if actor else None,
        payment_method=data.payment_method,
        payment_type=data.payment_type,
        total_amount=total,
        paid_amount=paid,
        pending_amount=pending,
        gst_amount=float(data.gst_amount),
        refunded_amount=0,
        payment_status=_derive_payment_status(paid, total),
        transaction_id=data.transaction_id,
        payment_date=data.payment_date,
        notes=data.notes,
    )
    db.add(payment)
    db.flush()
    payment.payment_code = _payment_code(payment.id)

    _sync_booking_payment_fields(db, booking)

    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if customer:
        _sync_customer_payment_fields(db, customer)

    log_audit(
        db,
        actor=actor,
        action="create_payment",
        entity_type="payment",
        entity_id=payment.id,
        new_values=serialize_payment(payment),
        request=request,
    )
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment)


def update_payment(
    db: Session,
    payment_id: int,
    data: PaymentUpdate,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    payment = get_payment_by_id(db, payment_id)
    old_values = serialize_payment(payment)

    for field in ["payment_method", "payment_type", "transaction_id", "payment_date", "notes"]:
        value = getattr(data, field)
        if value is not None:
            setattr(payment, field, value.strip() if isinstance(value, str) else value)

    if data.paid_amount is not None:
        payment.paid_amount = float(data.paid_amount)
        payment.pending_amount = max(0.0, float(payment.total_amount or 0) - float(data.paid_amount))
        payment.payment_status = _derive_payment_status(float(data.paid_amount), float(payment.total_amount or 0))

    if data.gst_amount is not None:
        payment.gst_amount = float(data.gst_amount)

    booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
    if booking:
        _sync_booking_payment_fields(db, booking)

    log_audit(
        db,
        actor=actor,
        action="update_payment",
        entity_type="payment",
        entity_id=payment.id,
        old_values=old_values,
        new_values=serialize_payment(payment),
        request=request,
    )
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment)


def update_payment_status(
    db: Session,
    payment_id: int,
    data: PaymentStatusUpdate,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    payment = get_payment_by_id(db, payment_id)
    old_values = serialize_payment(payment)
    payment.payment_status = data.payment_status

    booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
    if booking:
        _sync_booking_payment_fields(db, booking)
        customer = db.query(Customer).filter(Customer.id == payment.customer_id).first()
        if customer:
            _sync_customer_payment_fields(db, customer)

    log_audit(
        db,
        actor=actor,
        action="update_payment_status",
        entity_type="payment",
        entity_id=payment.id,
        old_values=old_values,
        new_values=serialize_payment(payment),
        request=request,
    )
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment)


def process_refund(
    db: Session,
    payment_id: int,
    data: RefundRequest,
    actor: Optional[User] = None,
    request: Optional[Request] = None,
) -> dict:
    payment = get_payment_by_id(db, payment_id)
    old_values = serialize_payment(payment)

    max_refundable = float(payment.paid_amount or 0) - float(payment.refunded_amount or 0)
    if float(data.amount) > max_refundable:
        raise HTTPException(
            status_code=400,
            detail=f"Refund amount exceeds refundable balance of {max_refundable}",
        )

    payment.refunded_amount = float(payment.refunded_amount or 0) + float(data.amount)
    payment.notes = f"{payment.notes or ''}\nRefund: {data.reason}".strip()
    if float(payment.refunded_amount) >= float(payment.paid_amount or 0):
        payment.payment_status = "refunded"

    booking = db.query(Booking).filter(Booking.id == payment.booking_id).first()
    if booking:
        _sync_booking_payment_fields(db, booking)
        customer = db.query(Customer).filter(Customer.id == payment.customer_id).first()
        if customer:
            _sync_customer_payment_fields(db, customer)

    log_audit(
        db,
        actor=actor,
        action="process_refund",
        entity_type="payment",
        entity_id=payment.id,
        old_values=old_values,
        new_values=serialize_payment(payment),
        request=request,
    )
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment)


def get_customer_payments(
    db: Session,
    customer_id: int,
    page: int = 1,
    limit: int = 20,
    payment_status: str = "",
    payment_method: str = "",
) -> dict:
    query = db.query(Payment).filter(Payment.customer_id == customer_id)

    if payment_status:
        query = query.filter(Payment.payment_status == payment_status.strip().lower())
    if payment_method:
        query = query.filter(Payment.payment_method == payment_method.strip().lower())

    query = query.order_by(Payment.id.desc())
    total = query.count()
    items = [serialize_payment(p) for p in query.offset((page - 1) * limit).limit(limit).all()]

    return {
        "items": items,
        "data": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)),
    }
