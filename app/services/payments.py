import logging
from datetime import timedelta
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.services.audit import log_audit
from app.models.bookings import Booking
from app.models.customers import Customer
from app.utils.money import as_aware_utc, money, money_str, to_minor_units, utcnow
from app.models.payments import Payment, PaymentHold, PaymentTransaction
from app.schemas.payments import PaymentAuthorize, PaymentCapture, PaymentCreate, PaymentStatusUpdate, PaymentUpdate, PaymentVoid, RefundRequest
from app.models.users import User

logger = logging.getLogger(__name__)

# A payment authorization is not a receipt and supplier acceptance is not the
# customer-facing final confirmation. Automated captures start only after the
# booking enters one of these confirmed lifecycle states.
FINAL_BOOKING_CONFIRMATION_STATUSES = frozenset({"confirmed", "ready_to_travel", "ongoing", "completed"})


def _payment_code(payment_id: int) -> str:
    return str(payment_id)


def _email_admin_payment_event(db: Session, payment: Payment, title: str, detail: str, event: str) -> None:
    """Operational mail is separate from the customer/agent receipt."""
    booking = payment.booking
    if not booking:
        return
    from app.config import settings
    from app.services.notification_delivery import dispatch_admin_lifecycle_emails
    from app.utils.email_templates import admin_booking_event_email
    admin_url = f"{settings.FRONTEND_URL}/admin/payments/{payment.id}"
    dispatch_admin_lifecycle_emails(
        db, event=event, entity_type="payment", entity_id=payment.id,
        template_key="admin_booking_event",
        values={"event_title": title, "detail": detail, "booking_code": booking.booking_code,
                "tour_name": booking.tour_name, "admin_url": admin_url,
                "button_text": "View payment", "button_url": admin_url},
        fallback_subject=f"{title} - {booking.booking_code}",
        fallback_html=admin_booking_event_email(title, detail, booking.booking_code, booking.tour_name, admin_url),
        event_version=str(payment.id),
    )


def _email_customer_payment_received(db: Session, payment: Payment, amount) -> None:
    booking = payment.booking
    customer = booking.customer if booking else None
    if not booking:
        return
    from app.config import settings
    from app.utils.email_templates import payment_received_email
    from app.services.notification_delivery import dispatch_lifecycle_email
    prior_paid = max(money(0), money(booking.amount_paid or 0) - money(amount))
    amount_pending = max(money(0), money(booking.final_amount or booking.total_cost or 0) - money(booking.amount_paid or 0))
    event = "deposit_payment_received" if payment.payment_type == "partial" else "balance_payment_received" if prior_paid > 0 else "payment_success"
    template_key = event if event in {"deposit_payment_received", "balance_payment_received"} else "payment_received"
    payment_summary = (
        f"Deposit paid: {booking.currency} {money_str(amount)}. Remaining balance: {booking.currency} {money_str(amount_pending)}"
        if event == "deposit_payment_received"
        else f"Payment received: {booking.currency} {money_str(amount)}"
    )
    if booking.booking_source != "agent" and customer and customer.email:
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        dispatch_lifecycle_email(
            db, event=event, entity_type="payment", entity_id=payment.id,
            recipient_type="customer", recipient_email=customer.email,
            template_key=template_key,
            values={"name": customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
                    "currency": booking.currency, "amount": amount, "amount_pending": amount_pending, "login_url": login_url,
                    "button_text": "View booking", "button_url": login_url},
            fallback_subject=f"Payment received - {booking.booking_code}",
            fallback_html=payment_received_email(customer.full_name, booking.booking_code, booking.tour_name, booking.currency, amount, login_url, payment_summary),
            event_version=str(payment.id),
        )
    # An agent who made the reservation is a booking party too: they need the
    # same payment receipt, while Tourvaa keeps an operational record.
    from app.services.notifications import enqueue_notification, notify_admins
    if booking.agent and booking.agent.user_id:
        enqueue_notification(db, user_id=booking.agent.user_id, notification_type="payment_received", title="Payment received", message=f"Payment of {booking.currency} {amount} was received for booking {booking.booking_code}.", entity_type="payment", entity_id=payment.id)
        if booking.agent.user and booking.agent.user.email:
            agent_url = f"{settings.FRONTEND_URL}/agent/bookings/{booking.id}"
            dispatch_lifecycle_email(
                db, event=event, entity_type="payment", entity_id=payment.id,
                recipient_type="agent", recipient_email=booking.agent.user.email,
                template_key=template_key,
                values={"name": booking.agent.agent_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "currency": booking.currency, "amount": amount, "amount_pending": amount_pending, "login_url": agent_url, "button_text": "View booking", "button_url": agent_url},
                fallback_subject=f"Payment received - {booking.booking_code}",
                fallback_html=payment_received_email(booking.agent.agent_name, booking.booking_code, booking.tour_name, booking.currency, amount, agent_url, payment_summary),
                event_version=str(payment.id),
            )
    notify_admins(db, notification_type="payment_received", title="Payment received", message=f"Payment of {booking.currency} {amount} was received for booking {booking.booking_code}.", entity_type="payment", entity_id=payment.id)
    _email_admin_payment_event(db, payment, "Payment received", f"Payment of {booking.currency} {amount} was received for booking {booking.booking_code}.", event)


def notify_payment_failed(db: Session, payment: Payment, reason: str) -> None:
    """Notify only after the gateway has authoritatively marked a payment failed."""
    booking = payment.booking
    if not booking:
        return
    from app.config import settings
    from app.services.notification_delivery import dispatch_lifecycle_email
    values = {"booking_code": booking.booking_code, "tour_name": booking.tour_name,
              "reason": reason or "Please retry your payment.", "login_url": ""}
    if booking.booking_source != "agent" and booking.customer and booking.customer.email:
        url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        dispatch_lifecycle_email(db, event="payment_failed", entity_type="payment", entity_id=payment.id,
            recipient_type="customer", recipient_email=booking.customer.email, template_key="payment_failed",
            values={**values, "name": booking.customer.full_name, "login_url": url},
            fallback_subject=f"Payment failed - {booking.booking_code}",
            fallback_html=f"<p>We could not complete payment for {booking.booking_code}. {reason}</p><p><a href='{url}'>Retry payment</a></p>", event_version=str(payment.id))
    if booking.agent and booking.agent.user and booking.agent.user.email:
        url = f"{settings.FRONTEND_URL}/agent/bookings/{booking.id}"
        dispatch_lifecycle_email(db, event="payment_failed", entity_type="payment", entity_id=payment.id,
            recipient_type="agent", recipient_email=booking.agent.user.email, template_key="payment_failed",
            values={**values, "name": booking.agent.agent_name, "login_url": url},
            fallback_subject=f"Payment failed - {booking.booking_code}",
            fallback_html=f"<p>We could not complete payment for {booking.booking_code}. {reason}</p><p><a href='{url}'>View booking</a></p>", event_version=str(payment.id))
    _email_admin_payment_event(db, payment, "Payment failure", f"Payment {payment.payment_code or payment.id} failed for booking {booking.booking_code}. Reason: {reason}", "payment_failed")


def _email_customer_refund_processed(db: Session, payment: Payment, amount) -> None:
    booking = payment.booking
    customer = booking.customer if booking else None
    if not booking:
        return
    from app.config import settings
    from app.utils.email_templates import refund_processed_email
    from app.services.notification_delivery import dispatch_lifecycle_email
    if booking.booking_source != "agent" and customer and customer.email:
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
        dispatch_lifecycle_email(
            db, event="refund_completed", entity_type="payment", entity_id=payment.id,
            recipient_type="customer", recipient_email=customer.email, template_key="refund_processed",
            values={"name": customer.full_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "currency": booking.currency, "amount": amount, "login_url": login_url, "button_text": "View booking", "button_url": login_url},
            fallback_subject=f"Refund processed - {booking.booking_code}",
            fallback_html=refund_processed_email(customer.full_name, booking.booking_code, booking.tour_name, booking.currency, amount, login_url),
            event_version=str(payment.id),
        )
    # Agent-owned reservations notify the agent, never the traveller record.
    if booking.agent and booking.agent.user and booking.agent.user.email:
        agent_url = f"{settings.FRONTEND_URL}/agent/bookings/{booking.id}"
        dispatch_lifecycle_email(
            db, event="refund_completed", entity_type="payment", entity_id=payment.id,
            recipient_type="agent", recipient_email=booking.agent.user.email, template_key="refund_processed",
            values={"name": booking.agent.agent_name, "booking_code": booking.booking_code, "tour_name": booking.tour_name, "currency": booking.currency, "amount": amount, "login_url": agent_url, "button_text": "View booking", "button_url": agent_url},
            fallback_subject=f"Refund processed - {booking.booking_code}",
            fallback_html=refund_processed_email(booking.agent.agent_name, booking.booking_code, booking.tour_name, booking.currency, amount, agent_url),
            event_version=str(payment.id),
        )


def _email_refund_initiated(db: Session, payment: Payment, amount) -> None:
    booking = payment.booking
    if not booking:
        return
    from app.services.notification_delivery import dispatch_lifecycle_email
    if booking.booking_source == "agent" and booking.agent and booking.agent.user and booking.agent.user.email:
        recipient_type, email, name = "agent", booking.agent.user.email, booking.agent.agent_name
        login_url = f"{settings.FRONTEND_URL}/agent/bookings/{booking.id}"
    elif booking.booking_source != "agent" and booking.customer and booking.customer.email:
        recipient_type, email, name = "customer", booking.customer.email, booking.customer.full_name
        login_url = f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
    else:
        return
    dispatch_lifecycle_email(
        db, event="refund_initiated", entity_type="payment", entity_id=payment.id,
        recipient_type=recipient_type, recipient_email=email, template_key="refund_initiated",
        values={"name": name, "booking_code": booking.booking_code, "tour_name": booking.tour_name,
                "currency": booking.currency, "amount": amount, "login_url": login_url,
                "button_text": "View booking", "button_url": login_url},
        fallback_subject=f"Refund initiated - {booking.booking_code}",
        fallback_html=f"<p>A refund of {booking.currency} {amount} has been initiated for booking {booking.booking_code}. We will notify you when it is completed.</p>",
        event_version=str(payment.gateway_payment_id or payment.id),
    )


def serialize_transaction(row: PaymentTransaction) -> dict:
    return {"id": row.id, "payment_id": row.payment_id, "booking_id": row.booking_id, "transaction_type": row.transaction_type, "amount": money_str(row.amount), "status": row.status, "gateway_reference": row.gateway_reference, "metadata": row.metadata_json, "created_at": row.created_at}


def serialize_hold(row: PaymentHold) -> dict:
    return {"id": row.id, "payment_id": row.payment_id, "booking_id": row.booking_id, "hold_amount": money_str(row.hold_amount), "captured_amount": money_str(row.captured_amount), "released_amount": money_str(row.released_amount), "status": row.status, "expires_at": row.expires_at, "created_at": row.created_at}


def serialize_payment(payment: Payment, detail: bool = False) -> dict:
    # Older payment rows may not have copied the booking's customer ID. The
    # booking remains the source of truth; agent bookings legitimately have no
    # direct customer and must not appear as a fictional customer.
    booking = payment.booking
    customer = payment.customer or (booking.customer if booking else None)
    customer_id = payment.customer_id or (booking.customer_id if booking else None)
    agent = booking.agent if booking else None
    data = {
        "id": payment.id,
        "payment_code": payment.payment_code or _payment_code(payment.id),
        "booking_id": payment.booking_id,
        "booking_code": booking.booking_code if booking else None,
        "currency": booking.currency if booking else "USD",
        "booking_source": booking.booking_source if booking else None,
        "customer_id": customer_id,
        "customer_name": customer.full_name if customer else None,
        "customer_email": customer.email if customer else None,
        "agent_id": booking.agent_id if booking else None,
        "agent_name": agent.agent_name if agent else None,
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
        "payment_date": payment.payment_date or payment.created_at,
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


def _status_after_payment_sync(booking: Booking, payment_status: str) -> str | None:
    """Return a booking status change without bypassing supplier acceptance
    (unless the tour opted out via requires_supplier_confirmation=False)."""
    if payment_status != "paid" or booking.booking_status not in {
        "pending_payment",
        "draft",
        "payment_authorized",
        "pending_credit_approval",
        "pending_supplier_acceptance",
    }:
        return None
    tour = getattr(booking, "tour", None)
    needs_supplier_confirmation = not tour or tour.requires_supplier_confirmation
    if booking.supplier_acceptance_status == "accepted":
        return "supplier_accepted"
    if needs_supplier_confirmation and booking.supplier_id:
        return "pending_supplier_acceptance"
    # Settlement never grants final confirmation.  Operations must either
    # assign a supplier or explicitly issue the Tourvaa confirmation.
    return "pending_supplier_assignment"


def _sync_booking_payment_fields(db: Session, booking: Booking) -> None:
    was_funded = booking.payment_status in {"paid", "partially_paid"}
    payments = db.query(Payment).filter(Payment.booking_id == booking.id).all()
    captured = sum(money(p.captured_amount or p.paid_amount or 0) for p in payments if p.payment_status not in {"voided", "failed"})
    refunded = sum(money(p.refunded_amount or 0) for p in payments)
    net_paid = max(money(0), money(captured) - money(refunded))
    final = money(booking.final_amount or booking.total_cost or 0)
    booking.amount_paid = net_paid
    if money(refunded) > 0:
        # A refunded booking doesn't still "owe" the refunded portion back to
        # Tourvaa - without this branch _derive_booking_status(net_paid=0, ...)
        # reports "unpaid" and amount_pending snaps back to the full price,
        # making a fully-refunded customer look like they still owe the whole
        # booking (see cancellations.py::process_refund, which hits this path
        # with no other code to correct it afterwards).
        booking.amount_pending = money(0)
        booking.payment_status = "refunded" if net_paid <= 0 else "partially_refunded"
    else:
        booking.amount_pending = max(money(0), final - net_paid)
        booking.payment_status = _derive_booking_status(net_paid, final)
    next_status = _status_after_payment_sync(booking, booking.payment_status)
    if next_status:
        booking.booking_status = next_status
    # A successful customer payment is already a real attributed conversion,
    # even while the booking waits for supplier acceptance. Record it now as
    # pending so it appears in the affiliate portal; payout eligibility still
    # remains gated by booking completion in affiliate_tracking.
    if booking.payment_status in {"paid", "partially_paid"} and booking.affiliate_ref_code:
        should_record_affiliate = booking.booking_source != "agent"
        if not should_record_affiliate:
            from app.services.settings import get_allow_agent_and_affiliate_same_booking
            should_record_affiliate = get_allow_agent_and_affiliate_same_booking(db)
        if should_record_affiliate:
            try:
                from app.services.affiliate_tracking import record_conversion
                from app.services.bookings import affiliate_eligible_amount, supplier_booking_currency
                record_conversion(db, ref_code=booking.affiliate_ref_code, booking_id=booking.id, booking_amount=affiliate_eligible_amount(booking), currency=supplier_booking_currency(booking))
            except Exception:
                logger.warning("Affiliate conversion recording failed for booking %s", booking.id, exc_info=True)
    if booking.payment_status in {"paid", "partially_paid"} and not was_funded:
        from app.services.bookings import notify_booking_received_after_payment
        notify_booking_received_after_payment(db, booking)


def active_authorized_amount(db: Session, booking_id: int) -> Decimal:
    """Funds currently held by the gateway but not captured yet.

    A gateway authorization must not be counted as captured revenue, but it
    does cover the customer's balance and therefore must prevent a duplicate
    Pay Now checkout for the same amount.
    """
    rows = db.query(Payment.authorized_amount, Payment.captured_amount).filter(
        Payment.booking_id == booking_id,
        Payment.payment_status == "authorized",
    ).all()
    return sum((max(money(0), money(authorized) - money(captured)) for authorized, captured in rows), money(0))


def _sync_customer_payment_fields(db: Session, customer: Customer) -> None:
    from sqlalchemy import func as sqlfunc
    paid = db.query(sqlfunc.coalesce(sqlfunc.sum(Payment.captured_amount), 0)).filter(Payment.customer_id == customer.id, Payment.payment_status.notin_(["voided", "failed"])).scalar()
    pending = db.query(sqlfunc.coalesce(sqlfunc.sum(Booking.amount_pending), 0)).filter(Booking.customer_id == customer.id).scalar()
    customer.total_amount_paid = money(paid or 0)
    customer.total_amount_pending = money(pending or 0)


def _transaction(db: Session, payment: Payment, transaction_type: str, amount, actor: User | None, status: str = "success", metadata: dict | None = None, gateway_reference: str | None = None):
    db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type=transaction_type, amount=money(amount), status=status, gateway_reference=gateway_reference or payment.gateway_payment_id or payment.transaction_id, metadata_json=metadata, created_by=actor.id if actor else None))


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
    if (
        role == "customer"
        and (not payment.booking or payment.booking.booking_source != "agent")
        and payment.customer
        and payment.customer.user_id == actor.id
    ):
        return
    booking = payment.booking
    if role == "supplier" and booking and booking.supplier and booking.supplier.user_id == actor.id:
        return
    if role == "agent" and booking and booking.agent and booking.agent.user_id == actor.id:
        return
    raise HTTPException(status_code=403, detail="Payment access denied")


def get_payments(db: Session, page: int = 1, limit: int = 20, search: str = "", customer_id: Optional[int] = None, booking_id: Optional[int] = None, payment_status: str = "", payment_method: str = "", gateway: str = "", start_date: str = "", end_date: str = "", actor: Optional[User] = None) -> dict:
    query = db.query(Payment).options(
        joinedload(Payment.booking).joinedload(Booking.customer),
        joinedload(Payment.booking).joinedload(Booking.agent),
        joinedload(Payment.customer),
    )
    role = _user_role(actor)
    if role == "supplier":
        query = query.join(Payment.booking).join(Booking.supplier).filter_by(user_id=actor.id)
    elif role == "agent":
        query = query.join(Payment.booking).join(Booking.agent).filter_by(user_id=actor.id)
    elif role == "customer":
        query = query.join(Payment.customer).join(Payment.booking).filter(Customer.user_id == actor.id)
        query = query.filter(Booking.booking_source != "agent")
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
    if gateway:
        query = query.filter(Payment.gateway == gateway.strip().lower())
    if start_date:
        query = query.filter(Payment.created_at >= start_date)
    if end_date:
        query = query.filter(Payment.created_at <= f"{end_date} 23:59:59")
    query = query.order_by(Payment.id.desc())
    total = query.count()
    items = [serialize_payment(p) for p in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


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
    outstanding = money(booking.amount_pending if booking.amount_pending is not None else booking.final_amount or 0)
    if paid > outstanding:
        raise HTTPException(status_code=400, detail=f"Paid amount cannot exceed the booking's outstanding balance of {outstanding:.2f}")
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
    if booking.booking_source != "agent" and booking.customer and booking.customer.user_id:
        enqueue_notification(db, user_id=booking.customer.user_id, notification_type="payment_success", title="Payment recorded", message=f"Payment for booking {booking.booking_code} was recorded", entity_type="payment", entity_id=payment.id)
    _email_customer_payment_received(db, payment, paid)
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
    outstanding = max(
        money(0),
        money(booking.amount_pending if booking.amount_pending is not None else booking.final_amount or booking.total_cost or 0)
        - active_authorized_amount(db, booking.id),
    )
    if amount > outstanding:
        raise HTTPException(status_code=400, detail=f"Authorization amount cannot exceed the booking's outstanding balance of {outstanding:.2f}")
    payment = Payment(booking_id=booking.id, customer_id=booking.customer_id, created_by=actor.id if actor else None, payment_method=data.payment_method, payment_type=data.payment_type, gateway=data.gateway, gateway_payment_id=data.gateway_payment_id, gateway_order_id=data.gateway_order_id, idempotency_key=data.idempotency_key, total_amount=money(booking.final_amount or booking.total_cost), authorized_amount=amount, captured_amount=money(0), paid_amount=money(0), pending_amount=money(booking.final_amount or booking.total_cost), payment_status="authorized", notes=data.notes)
    db.add(payment)
    db.flush()
    payment.payment_code = _payment_code(payment.id)
    db.add(PaymentHold(payment_id=payment.id, booking_id=booking.id, hold_amount=amount, status="active"))
    _transaction(db, payment, "authorize", amount, actor)
    booking.payment_status = "authorized"
    if booking.booking_status == "pending_payment":
        booking.booking_status = (
            "pending_supplier_acceptance"
            if booking.supplier_id and booking.supplier_acceptance_status == "pending"
            else "payment_authorized"
        )
    log_audit(db, actor=actor, action="authorize_payment", entity_type="payment", entity_id=payment.id, request=request)
    from app.services.notifications import notify_admins
    notify_admins(db, notification_type="payment_authorized", title="Payment authorized", message=f"Payment hold created for booking {booking.booking_code}", entity_type="payment", entity_id=payment.id)
    from app.services.bookings import notify_booking_received_after_payment
    notify_booking_received_after_payment(db, booking)
    db.commit()
    db.refresh(payment)
    return serialize_payment(payment, detail=True)


def record_gateway_authorization(db: Session, payment: Payment, *, gateway_reference: str, expires_at=None, actor: Optional[User] = None) -> Payment:
    """Record a provider-confirmed authorization without treating it as a charge.

    The gateway response remains the source of truth.  This is intentionally
    separate from ``capture_payment`` so a successful checkout never changes
    the booking to paid before the supplier has accepted it.
    """
    if payment.payment_status == "authorized":
        return payment
    if payment.payment_status != "pending":
        raise HTTPException(status_code=409, detail="Payment is no longer awaiting authorization")
    amount = money(payment.total_amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Authorization amount must be greater than zero")
    payment.authorized_amount = amount
    payment.pending_amount = amount
    payment.payment_status = "authorized"
    payment.gateway_payment_id = gateway_reference
    hold = db.query(PaymentHold).filter(PaymentHold.payment_id == payment.id, PaymentHold.status == "active").first()
    if not hold:
        # Tourvaa's operational window is four days. This is shorter than
        # Stripe's normal online-card window and PayPal's 29-day validity,
        # so the customer is never left with an open hold while a supplier
        # decision is unresolved.
        hold = PaymentHold(payment_id=payment.id, booking_id=payment.booking_id, hold_amount=amount, status="active")
        db.add(hold)
    policy_expiry = utcnow() + timedelta(days=4)
    hold.expires_at = min(as_aware_utc(expires_at), policy_expiry) if expires_at else policy_expiry
    _transaction(db, payment, "authorize", amount, actor, gateway_reference=gateway_reference)
    if payment.booking:
        payment.booking.payment_status = "authorized"
        if payment.booking.booking_status == "pending_payment":
            payment.booking.booking_status = "pending_supplier_acceptance" if payment.booking.supplier_id else "payment_authorized"
    if payment.booking:
        from app.services.bookings import notify_booking_received_after_payment
        notify_booking_received_after_payment(db, payment.booking)
    db.commit()
    db.refresh(payment)
    return payment


def capture_gateway_authorized_payment(db: Session, payment: Payment, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    """Capture a verified Stripe/PayPal authorization after final booking confirmation."""
    if payment.payment_status != "authorized":
        return serialize_payment(payment, detail=True)
    amount = money(payment.authorized_amount) - money(payment.captured_amount)
    if amount <= 0:
        return serialize_payment(payment, detail=True)
    if payment.gateway == "stripe":
        from app.services.payments_gateway import get_stripe
        if not payment.gateway_payment_id:
            raise HTTPException(status_code=400, detail="Stripe authorization has no PaymentIntent reference")
        stripe = get_stripe(db)

        def reconcile_succeeded_intent(intent: dict) -> bool:
            if intent.get("status") != "succeeded":
                return False
            expected_currency = ((payment.booking.currency if payment.booking else None) or "USD").lower()
            if str(intent.get("currency") or "").lower() != expected_currency:
                raise HTTPException(status_code=409, detail="Stripe capture currency does not match the booking currency")
            received = money(Decimal(str(intent.get("amount_received") or 0)) / 100)
            if received != amount:
                raise HTTPException(status_code=409, detail="Stripe captured amount does not match the remaining authorization")
            return True

        # A webhook may have been delayed/lost after Stripe captured the
        # intent. Query Stripe before capture so an operator retry reconciles
        # the local row instead of treating an already-successful charge as a
        # 502 gateway failure.
        intent = stripe.retrieve_payment_intent(payment.gateway_payment_id)
        if not reconcile_succeeded_intent(intent):
            try:
                intent = stripe.capture_payment_intent(payment.gateway_payment_id, to_minor_units(amount), f"capture:{payment.id}")
            except HTTPException:
                # A concurrent capture can complete after the preflight read.
                # Re-read the provider state once and reconcile only a fully
                # verified successful capture.
                intent = stripe.retrieve_payment_intent(payment.gateway_payment_id)
                if not reconcile_succeeded_intent(intent):
                    raise
    elif payment.gateway == "paypal":
        from app.services.payments_gateway import get_paypal
        currency = (payment.booking.currency if payment.booking else None) or "USD"
        get_paypal(db).capture_authorization(payment.gateway_payment_id, str(amount), currency, f"capture:{payment.id}")
    return capture_payment(db, payment.id, PaymentCapture(amount=amount, transaction_id=payment.gateway_payment_id, notes="Captured after booking confirmation"), actor=actor, request=request)


def capture_authorized_payment_for_operator(db: Session, payment_id: int, data: PaymentCapture, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    """Capture through the real provider when the authorization is gateway-held.

    The admin UI must never mark a Stripe/PayPal payment paid merely because
    an operator clicked Capture. Gateway-held authorizations are full-capture
    only in this workflow, so reject a mismatched amount before making the
    provider call.
    """
    payment = get_payment_by_id(db, payment_id, for_update=True)
    available = money(payment.authorized_amount or payment.total_amount) - money(payment.captured_amount)
    if payment.gateway in {"stripe", "paypal"} and payment.payment_status == "authorized":
        if money(data.amount) != available:
            raise HTTPException(status_code=400, detail="Gateway authorization must be captured for its full remaining amount")
        return capture_gateway_authorized_payment(db, payment, actor=actor, request=request)
    return capture_payment(db, payment_id, data, actor=actor, request=request)


def record_gateway_capture_failure(db: Session, payment_id: int, error: Exception | str) -> None:
    """Persist an actionable capture failure after the caller rolled back.

    A supplier acceptance is valid even when a gateway is temporarily down.
    The failure must nevertheless be durable and visible; logging alone leaves
    an authorized hold stranded without an operator or retry path.
    """
    payment = get_payment_by_id(db, payment_id, for_update=True)
    if payment.payment_status != "authorized":
        return
    message = str(error).strip() or "Gateway capture failed"
    payment.failure_reason = message[:255]
    _transaction(
        db, payment, "capture", money(0), None, status="failed",
        metadata={"reason": payment.failure_reason, "retryable": payment.gateway in {"stripe", "paypal"}},
    )
    from app.services.notifications import notify_admins
    notify_admins(
        db,
        notification_type="payment_failed",
        title="Payment capture needs attention",
        message=f"Could not capture authorized payment {payment.payment_code} for booking {payment.booking.booking_code if payment.booking else payment.booking_id}. It will retry automatically.",
        entity_type="payment",
        entity_id=payment.id,
        event_key="gateway_capture_failed",
        # One admin alert per payment; attempts remain visible in transactions.
        event_version=str(payment.id),
    )
    db.commit()


def retry_authorized_gateway_captures(db: Session) -> list[int]:
    """Retry capture only for finally confirmed bookings with an active hold.

    The provider idempotency key is stable per payment, and capture_payment
    atomically changes the local row to paid. Repeated workers therefore cannot
    charge or notify twice. Expired holds remain handled by the separate hold
    release sweep.
    """
    rows = (
        db.query(Payment)
        .join(Booking, Booking.id == Payment.booking_id)
        .filter(
            Payment.payment_status == "authorized",
            Payment.gateway.in_(["stripe", "paypal"]),
            Booking.supplier_acceptance_status == "accepted",
            Booking.booking_status.in_(FINAL_BOOKING_CONFIRMATION_STATUSES),
        )
        .all()
    )
    captured: list[int] = []
    for row in rows:
        try:
            capture_gateway_authorized_payment(db, row)
            captured.append(row.id)
        except Exception as error:
            db.rollback()
            logger.exception("Scheduled gateway capture retry failed for payment %s", row.id)
            try:
                record_gateway_capture_failure(db, row.id, error)
            except Exception:
                db.rollback()
                logger.exception("Could not persist gateway capture failure for payment %s", row.id)
    return captured


def release_gateway_authorized_payment(db: Session, payment: Payment, reason: str, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    """Release an uncaptured hold at the provider, then update local state."""
    if payment.payment_status != "authorized":
        return serialize_payment(payment, detail=True)
    if payment.gateway == "stripe":
        from app.services.payments_gateway import get_stripe
        get_stripe(db).cancel_payment_intent(payment.gateway_payment_id, f"void:{payment.id}")
    elif payment.gateway == "paypal":
        from app.services.payments_gateway import get_paypal
        get_paypal(db).void_authorization(payment.gateway_payment_id, f"void:{payment.id}")
    return void_payment(db, payment.id, PaymentVoid(reason=reason), actor=actor, request=request)


def release_expired_gateway_holds(db: Session) -> list[int]:
    """Release four-day holds; called by the durable hourly scheduler."""
    expired = []
    for hold in db.query(PaymentHold).filter(PaymentHold.status == "active", PaymentHold.expires_at.isnot(None)).all():
        if as_aware_utc(hold.expires_at) > utcnow():
            continue
        payment = db.query(Payment).filter(Payment.id == hold.payment_id).first()
        if not payment or payment.payment_status != "authorized":
            continue
        try:
            release_gateway_authorized_payment(db, payment, "Authorization expired before booking confirmation")
            expired.append(payment.id)
        except Exception:
            logger.exception("Could not release expired gateway hold for payment %s", payment.id)
            db.rollback()
    return expired


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
    # payments.payment_date is a legacy VARCHAR(30). Keep a stable UTC value
    # within that limit; datetime.isoformat() with microseconds and +00:00 is
    # 32 characters and causes MySQL to reject an otherwise valid capture.
    payment.payment_date = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    payment.payment_status = _derive_booking_status(payment.captured_amount, payment.total_amount)
    payment.failure_reason = None
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
    if payment.booking and payment.booking.booking_source != "agent" and payment.booking.customer and payment.booking.customer.user_id:
        enqueue_notification(db, user_id=payment.booking.customer.user_id, notification_type="payment_captured", title="Payment captured", message=f"Payment for booking {payment.booking.booking_code} was captured", entity_type="payment", entity_id=payment.id)
    log_audit(db, actor=actor, action="capture_payment", entity_type="payment", entity_id=payment.id, request=request)
    _email_customer_payment_received(db, payment, amount)
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
    if data.paid_amount is not None:
        raise HTTPException(
            status_code=409,
            detail="Payment amounts and status are updated by gateway events or approved capture, void, and refund operations.",
        )
    old_values = serialize_payment(payment)
    for field in ["payment_method", "payment_type", "transaction_id", "payment_date", "notes"]:
        value = getattr(data, field)
        if value is not None:
            setattr(payment, field, value.strip() if isinstance(value, str) else value)
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
    # A status is a derived record of a real financial event, not an editable
    # admin field. Gateway webhooks, capture, void and refund operations are
    # the only supported state-transition paths. Looking up first preserves
    # the existing 404 response for an unknown payment.
    get_payment_by_id(db, payment_id)
    raise HTTPException(
        status_code=409,
        detail="Payment status is updated automatically from gateway events or approved capture, void, and refund operations.",
    )


def _issue_gateway_refund(db: Session, payment: Payment, amount, reason: str) -> tuple[Optional[str], Optional[str]]:
    """Actually call out to Stripe/PayPal to refund money for gateway-captured
    payments. Returns (gateway_refund_id, gateway_status). Manual/test
    payments have no live gateway to call, so this returns (None, None) and
    the caller falls back to local-only bookkeeping.

    Raises HTTPException (502/400) if the live refund call fails - callers
    must not mutate local refund state until this succeeds, so a failed
    gateway call never desyncs local records from what actually happened
    with the customer's money.
    """
    from app.services.payments_gateway import get_paypal, get_stripe

    gateway = (payment.gateway or "").lower()
    if gateway not in ("stripe", "paypal"):
        return None, None

    # Deterministic per-attempt idempotency key: a retry of the exact same
    # refund (same payment, same balance-before, same amount) reuses the key,
    # while a distinct subsequent partial refund gets a new one because
    # refunded_amount has moved on.
    idempotency_key = f"refund:{payment.id}:{money_str(payment.refunded_amount)}:{money_str(amount)}"

    if gateway == "stripe":
        if not payment.gateway_payment_id:
            raise HTTPException(status_code=400, detail="Payment has no Stripe payment intent on record; cannot issue a gateway refund")
        stripe = get_stripe(db)
        result = stripe.create_refund(
            payment_intent_id=payment.gateway_payment_id,
            amount_cents=to_minor_units(amount),
            reason=reason or "requested_by_customer",
            idempotency_key=idempotency_key,
        )
        return result.get("id"), result.get("status")

    if not payment.gateway_payment_id:
        raise HTTPException(status_code=400, detail="Payment has no PayPal capture id on record; cannot issue a gateway refund")
    paypal = get_paypal(db)
    currency = (payment.booking.currency if payment.booking else None) or "USD"
    result = paypal.create_refund(
        capture_id=payment.gateway_payment_id,
        amount=str(amount),
        currency=currency,
        note=reason or "Refund",
        idempotency_key=idempotency_key,
    )
    return result.get("id"), result.get("status")


def process_refund(db: Session, payment_id: int, data: RefundRequest, actor: Optional[User] = None, request: Optional[Request] = None) -> dict:
    payment = get_payment_by_id(db, payment_id, for_update=True)
    max_refundable = money(payment.captured_amount or payment.paid_amount) - money(payment.refunded_amount)
    amount = money(data.amount)
    if amount > max_refundable:
        raise HTTPException(status_code=400, detail=f"Refund amount exceeds refundable balance of {money_str(max_refundable)}")

    # Call the real gateway (if any) BEFORE touching local state, so a failed
    # gateway call never leaves local records claiming money moved when it didn't.
    try:
        gateway_refund_id, gateway_status = _issue_gateway_refund(db, payment, amount, data.reason or "")
    except HTTPException as error:
        # Local state is untouched, but a refund that could not be issued must
        # not fail silently - alert admins so it gets retried or handled manually.
        from app.services.notifications import notify_admins
        notify_admins(
            db,
            notification_type="refund_failed",
            title="Refund failed",
            message=f"Gateway refund of {money_str(amount)} for {payment.payment_code} failed: {error.detail}",
            entity_type="payment",
            entity_id=payment.id,
        )
        _email_admin_payment_event(
            db, payment, "Refund failed",
            f"Gateway refund of {money_str(amount)} for {payment.payment_code} failed: {error.detail}",
            "refund_failed",
        )
        db.commit()
        raise

    normalized_gateway_status = str(gateway_status or "").lower()
    if gateway_refund_id and normalized_gateway_status not in {"succeeded", "completed"}:
        payment.payment_status = "refund_pending"
        _transaction(db, payment, "refund_pending", amount, actor, metadata={"reason": data.reason, "gateway_status": gateway_status}, gateway_reference=gateway_refund_id)
        log_audit(db, actor=actor, action="initiate_refund", entity_type="payment", entity_id=payment.id, new_values={"gateway_refund_id": gateway_refund_id, "gateway_status": gateway_status}, request=request)
        _email_refund_initiated(db, payment, amount)
        _email_admin_payment_event(db, payment, "Refund initiated", f"Refund of {money_str(amount)} is pending at the payment provider for {payment.payment_code}.", "refund_initiated")
        db.commit(); db.refresh(payment)
        result = serialize_payment(payment, detail=True)
        result["gateway_refund_id"] = gateway_refund_id
        result["refund_pending"] = True
        return result

    payment.refunded_amount = money(payment.refunded_amount) + amount
    if money(payment.refunded_amount) >= money(payment.captured_amount or payment.paid_amount):
        payment.payment_status = "refunded"
    else:
        payment.payment_status = "partially_refunded"
    _transaction(db, payment, "refund", amount, actor, metadata={"reason": data.reason, "gateway_status": gateway_status}, gateway_reference=gateway_refund_id)
    if payment.booking:
        _sync_booking_payment_fields(db, payment.booking)
    from app.services.notifications import enqueue_notification, notify_admins
    notify_admins(db, notification_type="payment_refunded", title="Payment refunded", message=f"Refund processed for {payment.payment_code}", entity_type="payment", entity_id=payment.id)
    if payment.booking and payment.booking.booking_source != "agent" and payment.booking.customer and payment.booking.customer.user_id:
        enqueue_notification(db, user_id=payment.booking.customer.user_id, notification_type="payment_refunded", title="Payment refunded", message=f"Refund processed for {payment.payment_code}", entity_type="payment", entity_id=payment.id)
    log_audit(db, actor=actor, action="process_refund", entity_type="payment", entity_id=payment.id, new_values={"gateway_refund_id": gateway_refund_id}, request=request)
    db.commit()
    db.refresh(payment)
    _email_customer_refund_processed(db, payment, amount)
    _email_admin_payment_event(
        db, payment, "Refund completed",
        f"Refund of {money_str(amount)} was processed for payment {payment.payment_code}.",
        "refund_completed",
    )
    db.commit()
    result = serialize_payment(payment, detail=True)
    result["gateway_refund_id"] = gateway_refund_id
    return result


def get_customer_payments(
    db: Session,
    customer_id: int,
    page: int = 1,
    limit: int = 20,
    payment_status: str = "",
    payment_method: str = "",
    actor: Optional[User] = None,
    hide_identifiers: Optional[bool] = None,
) -> dict:
    result = get_payments(
        db, page=page, limit=limit, customer_id=customer_id,
        payment_status=payment_status, payment_method=payment_method, actor=actor,
    )
    # A payment's database/code identifier is an internal finance reference.
    # Travellers in public/portal contexts navigate from booking codes, while
    # administrative staff retain the identifiers in the Admin screens.
    should_hide = hide_identifiers if hide_identifiers is not None else (actor is None)
    if should_hide:
        for item in result["items"]:
            item.pop("id", None)
            item.pop("payment_code", None)
    return result
