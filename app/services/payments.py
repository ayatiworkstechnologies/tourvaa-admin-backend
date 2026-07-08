import logging
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.services.audit import log_audit
from app.models.bookings import Booking
from app.models.customers import Customer
from app.utils.money import money, money_str, utcnow
from app.models.payments import Payment, PaymentHold, PaymentTransaction
from app.schemas.payments import PaymentAuthorize, PaymentCapture, PaymentCreate, PaymentStatusUpdate, PaymentUpdate, PaymentVoid, RefundRequest
from app.models.users import User

logger = logging.getLogger(__name__)


def _payment_code(payment_id: int) -> str:
    return f"PAY-{payment_id:06d}"


def serialize_transaction(row: PaymentTransaction) -> dict:
    return {"id": row.id, "payment_id": row.payment_id, "booking_id": row.booking_id, "transaction_type": row.transaction_type, "amount": money_str(row.amount), "status": row.status, "gateway_reference": row.gateway_reference, "metadata": row.metadata_json, "created_at": row.created_at}


def serialize_hold(row: PaymentHold) -> dict:
    return {"id": row.id, "payment_id": row.payment_id, "booking_id": row.booking_id, "hold_amount": money_str(row.hold_amount), "captured_amount": money_str(row.captured_amount), "released_amount": money_str(row.released_amount), "status": row.status, "expires_at": row.expires_at, "created_at": row.created_at}


def serialize_payment(payment: Payment, detail: bool = False) -> dict:
    data = {
        "id": payment.id,
        "payment_code": payment.payment_code or _payment_code(payment.id),
        "booking_id": payment.booking_id,
        "booking_code": payment.booking.booking_code if payment.booking else None,
        "customer_id": payment.customer_id,
        "customer_name": payment.customer.full_name if payment.customer else None,
        "customer_email": payment.customer.email if payment.customer else None,
        "payment_method": payment.payment_method,
        "payment_type": payment.payment_type,
        "gateway": payment.gateway,
        "gateway_payment_id": payment.gateway_payment_id,
        "gateway_order_id": payment.gateway_order_id,
        "idempotency_key": payment.idempotency_key,
        "total_amount": money_str(payment.total_amount),
        "authorized_amount": money_str(payment.authorized_amount),
        "captured_amount": money_str(payment.captured_amount),
        "paid_amount": money_str(payment.paid_amount),
        "pending_amount": money_str(payment.pending_amount),
        "gst_amount": money_str(payment.gst_amount),
        "surcharge_amount": money_str(payment.surcharge_amount),
        "refunded_amount": money_str(payment.refunded_amount),
        "payment_status": payment.payment_status,
        "transaction_id": payment.transaction_id,
        "payment_date": payment.payment_date,
        "notes": payment.notes,
        "failure_reason": payment.failure_reason,
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
    }
    if detail:
        data["transactions"] = [serialize_transaction(t) for t in payment.transactions]
        data["holds"] = [serialize_hold(h) for h in payment.holds]
    return data


def _derive_booking_status(net_paid, final_amount) -> str:
    net_paid = money(net_paid); final_amount = money(final_amount)
    if net_paid <= 0:
        return "unpaid"
    if net_paid >= final_amount:
        return "paid"
    return "partially_paid"


def _sync_booking_payment_fields(db: Session, booking: Booking) -> None:
    payments = db.query(Payment).filter(Payment.booking_id == booking.id).all()
    captured = sum(money(p.captured_amount or p.paid_amount or 0) for p in payments if p.payment_status not in {"voided", "failed"})
    refunded = sum(money(p.refunded_amount or 0) for p in payments)
    net_paid = max(money(0), money(captured) - money(refunded))
    final = money(booking.final_amount or booking.total_cost or 0)
    booking.amount_paid = net_paid
    booking.amount_pending = max(money(0), final - net_paid)
    booking.payment_status = _derive_booking_status(net_paid, final)
    if booking.payment_status == "paid" and booking.booking_status in {"pending_payment", "draft", "payment_authorized"}:
        booking.booking_status = "confirmed"


def _sync_customer_payment_fields(db: Session, customer: Customer) -> None:
    from sqlalchemy import func as sqlfunc
    paid = db.query(sqlfunc.coalesce(sqlfunc.sum(Payment.captured_amount), 0)).filter(Payment.customer_id == customer.id, Payment.payment_status.notin_(["voided", "failed"])).scalar()
    pending = db.query(sqlfunc.coalesce(sqlfunc.sum(Booking.amount_pending), 0)).filter(Booking.customer_id == customer.id).scalar()
    customer.total_amount_paid = money(paid or 0)
    customer.total_amount_pending = money(pending or 0)


def _transaction(db: Session, payment: Payment, transaction_type: str, amount, actor: User | None, status: str = "success", metadata: dict | None = None):
    db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type=transaction_type, amount=money(amount), status=status, gateway_reference=payment.gateway_payment_id or payment.transaction_id, metadata_json=metadata, created_by=actor.id if actor else None))


def get_payment_by_id(db: Session, payment_id: int, for_update: bool = False) -> Payment:
    query = db.query(Payment).filter(Payment.id == payment_id)
    if for_update:
        query = query.with_for_update()
    payment = query.first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


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


def _ensure_payment_access(payment: Payment, actor: User | None) -> None:
    role = _user_role(actor)
    if role == "admin" or actor is None:
        return
    if role == "customer" and payment.customer and payment.customer.user_id == actor.id:
        return
    booking = payment.booking
    if role == "supplier" and booking and booking.supplier and booking.supplier.user_id == actor.id:
        return
    if role == "agent" and booking and booking.agent and booking.agent.user_id == actor.id:
        return
    raise HTTPException(status_code=403, detail="Payment access denied")


def get_payments(db: Session, page: int = 1, limit: int = 20, search: str = "", customer_id: Optional[int] = None, booking_id: Optional[int] = None, payment_status: str = "", payment_method: str = "", start_date: str = "", end_date: str = "", actor: Optional[User] = None) -> dict:
    query = db.query(Payment).options(joinedload(Payment.booking), joinedload(Payment.customer))
    role = _user_role(actor)
    if role == "supplier":
        query = query.join(Payment.booking).join(Booking.supplier).filter_by(user_id=actor.id)
    elif role == "agent":
        query = query.join(Payment.booking).join(Booking.agent).filter_by(user_id=actor.id)
    elif role == "customer":
        query = query.join(Payment.customer).filter_by(user_id=actor.id)
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.outerjoin(Booking, Booking.id == Payment.booking_id).outerjoin(Customer, Customer.id == Payment.customer_id).filter(
            or_(
                Payment.payment_code.ilike(pattern),
                Payment.transaction_id.ilike(pattern),
                Payment.gateway_payment_id.ilike(pattern),
                Booking.booking_code.ilike(pattern),
                Customer.full_name.ilike(pattern),
                Customer.email.ilike(pattern),
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
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def get_payment_detail(db: Session, payment_id: int, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id)
    _ensure_payment_access(payment, actor)
    log_audit(db, actor=actor, action="view_payment", entity_type="payment", entity_id=payment.id, request=request)
    db.commit()
    return serialize_payment(payment, detail=True)


def create_payment(db: Session, data: PaymentCreate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.customer_id != data.customer_id:
        raise HTTPException(status_code=400, detail="Customer does not match booking")
    paid = money(data.paid_amount)
    total = money(data.total_amount)
    payment = Payment(booking_id=data.booking_id, customer_id=data.customer_id, created_by=actor.id if actor else None, payment_method=data.payment_method, payment_type=data.payment_type, gateway=data.gateway, gateway_payment_id=data.gateway_payment_id, gateway_order_id=data.gateway_order_id, idempotency_key=data.idempotency_key, total_amount=total, authorized_amount=money(0), captured_amount=paid, paid_amount=paid, pending_amount=max(money(0), total - paid), gst_amount=money(data.gst_amount), surcharge_amount=money(data.surcharge_amount), refunded_amount=money(0), payment_status=_derive_booking_status(paid, total), transaction_id=data.transaction_id, payment_date=data.payment_date, notes=data.notes)
    db.add(payment)
    db.flush()
    payment.payment_code = _payment_code(payment.id)
    _transaction(db, payment, "payment", paid, actor)
    _sync_booking_payment_fields(db, booking)
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if customer:
        _sync_customer_payment_fields(db, customer)
    log_audit(db, actor=actor, action="create_payment", entity_type="payment", entity_id=payment.id, new_values=serialize_payment(payment), request=request)
    from app.services.notifications import enqueue_notification, notify_admins
    notify_admins(db, notification_type="payment_success", title="Payment recorded", message=f"Payment {payment.payment_code} was recorded", entity_type="payment", entity_id=payment.id)
    if booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="payment_success", title="Payment recorded", message=f"Payment {payment.payment_code} was recorded", entity_type="payment", entity_id=payment.id)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def authorize_payment(db: Session, data: PaymentAuthorize, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    booking = db.query(Booking).filter(Booking.id == data.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    existing = db.query(Payment).filter(Payment.idempotency_key == data.idempotency_key).first() if data.idempotency_key else None
    if existing:
        return serialize_payment(existing, detail=True)
    amount = money(data.amount)
    payment = Payment(booking_id=booking.id, customer_id=booking.customer_id, created_by=actor.id if actor else None, payment_method=data.payment_method, payment_type=data.payment_type, gateway=data.gateway, gateway_payment_id=data.gateway_payment_id, gateway_order_id=data.gateway_order_id, idempotency_key=data.idempotency_key, total_amount=money(booking.final_amount or booking.total_cost), authorized_amount=amount, captured_amount=money(0), paid_amount=money(0), pending_amount=money(booking.final_amount or booking.total_cost), payment_status="authorized", notes=data.notes)
    db.add(payment)
    db.flush()
    payment.payment_code = _payment_code(payment.id)
    db.add(PaymentHold(payment_id=payment.id, booking_id=booking.id, hold_amount=amount, status="active"))
    _transaction(db, payment, "authorize", amount, actor)
    booking.payment_status = "authorized"
    if booking.booking_status == "pending_payment":
        booking.booking_status = "payment_authorized"
    log_audit(db, actor=actor, action="authorize_payment", entity_type="payment", entity_id=payment.id, request=request)
    from app.services.notifications import notify_admins
    notify_admins(db, notification_type="payment_authorized", title="Payment authorized", message=f"Payment hold created for booking {booking.booking_code}", entity_type="payment", entity_id=payment.id)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def capture_payment(db: Session, payment_id: int, data: PaymentCapture, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id, for_update=True)
    amount = money(data.amount)
    available = money(payment.authorized_amount or payment.total_amount) - money(payment.captured_amount)
    if amount > available:
        raise HTTPException(status_code=400, detail="Capture amount exceeds available authorized amount")
    payment.captured_amount = money(payment.captured_amount) + amount
    payment.paid_amount = payment.captured_amount
    payment.pending_amount = max(money(0), money(payment.total_amount) - money(payment.captured_amount))
    payment.transaction_id = data.transaction_id or payment.transaction_id
    payment.payment_date = utcnow().isoformat()
    payment.payment_status = _derive_booking_status(payment.captured_amount, payment.total_amount)
    hold = db.query(PaymentHold).filter(PaymentHold.payment_id == payment.id, PaymentHold.status == "active").first()
    if hold:
        hold.captured_amount = money(hold.captured_amount) + amount
        if money(hold.captured_amount) >= money(hold.hold_amount):
            hold.status = "captured"
    _transaction(db, payment, "capture", amount, actor)
    if payment.booking:
        _sync_booking_payment_fields(db, payment.booking)
    from app.services.notifications import enqueue_notification, notify_admins
    from app.schemas.invoices import InvoiceGenerateRequest
    from app.services.invoices import generate_invoice
    notify_admins(db, notification_type="payment_captured", title="Payment captured", message=f"Payment {payment.payment_code} was captured", entity_type="payment", entity_id=payment.id)
    if payment.booking and payment.booking.customer and payment.booking.customer.user_id:
        enqueue_notification(db, user_id=payment.booking.customer.user_id, notification_type="payment_captured", title="Payment captured", message=f"Payment {payment.payment_code} was captured", entity_type="payment", entity_id=payment.id)
    log_audit(db, actor=actor, action="capture_payment", entity_type="payment", entity_id=payment.id, request=request)
    db.commit()
    db.refresh(payment)
    try:
        generate_invoice(db, InvoiceGenerateRequest(booking_id=payment.booking_id, payment_id=payment.id), actor, request)
    except Exception as error:
        logger.warning("Invoice generation after payment capture failed for payment %s: %s", payment.id, error)
    return serialize_payment(payment, detail=True)


def void_payment(db: Session, payment_id: int, data: PaymentVoid, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id, for_update=True)
    if money(payment.captured_amount) > 0:
        raise HTTPException(status_code=400, detail="Captured payments cannot be voided; refund instead")
    payment.payment_status = "voided"
    for hold in payment.holds:
        if hold.status == "active":
            hold.released_amount = money(hold.hold_amount) - money(hold.captured_amount)
            hold.status = "released"
    _transaction(db, payment, "void", money(payment.authorized_amount), actor, metadata={"reason": data.reason})
    if payment.booking:
        _sync_booking_payment_fields(db, payment.booking)
    log_audit(db, actor=actor, action="void_payment", entity_type="payment", entity_id=payment.id, request=request)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def update_payment(db: Session, payment_id: int, data: PaymentUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id)
    old_values = serialize_payment(payment)
    for field in ["payment_method", "payment_type", "transaction_id", "payment_date", "notes"]:
        value = getattr(data, field)
        if value is not None:
            setattr(payment, field, value.strip() if isinstance(value, str) else value)
    if data.paid_amount is not None:
        payment.paid_amount = money(data.paid_amount)
        payment.captured_amount = money(data.paid_amount)
        payment.pending_amount = max(money(0), money(payment.total_amount) - money(data.paid_amount))
        payment.payment_status = _derive_booking_status(payment.paid_amount, payment.total_amount)
    if data.gst_amount is not None:
        payment.gst_amount = money(data.gst_amount)
    if data.surcharge_amount is not None:
        payment.surcharge_amount = money(data.surcharge_amount)
    if payment.booking:
        _sync_booking_payment_fields(db, payment.booking)
    log_audit(db, actor=actor, action="update_payment", entity_type="payment", entity_id=payment.id, old_values=old_values, new_values=serialize_payment(payment), request=request)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def update_payment_status(db: Session, payment_id: int, data: PaymentStatusUpdate, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id)
    old_values = serialize_payment(payment)
    payment.payment_status = data.payment_status
    if payment.booking:
        _sync_booking_payment_fields(db, payment.booking)
    log_audit(db, actor=actor, action="update_payment_status", entity_type="payment", entity_id=payment.id, old_values=old_values, new_values=serialize_payment(payment), request=request)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def process_refund(db: Session, payment_id: int, data: RefundRequest, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id, for_update=True)
    max_refundable = money(payment.captured_amount or payment.paid_amount) - money(payment.refunded_amount)
    amount = money(data.amount)
    if amount > max_refundable:
        raise HTTPException(status_code=400, detail=f"Refund amount exceeds refundable balance of {money_str(max_refundable)}")
    payment.refunded_amount = money(payment.refunded_amount) + amount
    if money(payment.refunded_amount) >= money(payment.captured_amount or payment.paid_amount):
        payment.payment_status = "refunded"
    else:
        payment.payment_status = "partially_refunded"
    _transaction(db, payment, "refund", amount, actor, metadata={"reason": data.reason})
    if payment.booking:
        _sync_booking_payment_fields(db, payment.booking)
    from app.services.notifications import enqueue_notification, notify_admins
    notify_admins(db, notification_type="payment_refunded", title="Payment refunded", message=f"Refund processed for {payment.payment_code}", entity_type="payment", entity_id=payment.id)
    if payment.booking and payment.booking.customer and payment.booking.customer.user_id:
        enqueue_notification(db, user_id=payment.booking.customer.user_id, notification_type="payment_refunded", title="Payment refunded", message=f"Refund processed for {payment.payment_code}", entity_type="payment", entity_id=payment.id)
    log_audit(db, actor=actor, action="process_refund", entity_type="payment", entity_id=payment.id, request=request)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def get_customer_payments(db: Session, customer_id: int, page: int = 1, limit: int = 20, payment_status: str = "", payment_method: str = "", actor: Optional[User] = None) -> dict:
    return get_payments(db, page=page, limit=limit, customer_id=customer_id, payment_status=payment_status, payment_method=payment_method, actor=actor)




