"""
Gateway-specific payment routes:
  POST /payments/stripe/create-session
  POST /payments/stripe/webhook
  POST /payments/paypal/create-order
  POST /payments/paypal/capture
  POST /payments/paypal/webhook
  POST /payments/test/simulate   (non-production only)
  GET  /payments/gateways/status (reports which gateways are configured)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.bookings import Booking
from app.auth.permissions import get_current_user
from app.utils.money import as_aware_utc, money, to_minor_units, utcnow
from app.utils.ratelimit import check_rate_limit
from app.services.payments_gateway import get_paypal, get_stripe
from app.services.settings import get_default_deposit_cutoff_days, get_default_deposit_percentage
from app.models.payments import Payment, PaymentTransaction
from app.services.payments import _payment_code, _sync_booking_payment_fields, record_gateway_authorization

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payment Gateways"])


def _require_paypal_amount(amount_container: dict, context: str) -> Decimal:
    """PayPal always includes resource.amount.value on real capture/refund
    events - a missing or unparseable value means a malformed payload, which
    must reject rather than silently move money at 0.00 (see PAY-02)."""
    amount_value = amount_container.get("value")
    if amount_value is None:
        raise HTTPException(status_code=400, detail=f"PayPal {context} event is missing amount.value")
    try:
        return money(Decimal(str(amount_value)))
    except (ArithmeticError, ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=f"PayPal {context} event has an unparseable amount.value") from error


def _require_captured_amount_matches_pending(payment: Payment, captured_amount: Decimal, gateway: str) -> Decimal:
    """Only settle the exact amount the customer was sent to the gateway for.

    A gateway payment record is created before redirecting the customer. Its
    ``total_amount`` is the authoritative amount for that checkout attempt
    (deposit or balance), not the booking's full price.
    """
    expected = money(payment.total_amount or 0)
    captured = money(captured_amount)
    if expected <= 0 or captured <= 0:
        raise HTTPException(status_code=400, detail=f"{gateway} capture amount must be greater than zero")
    if captured != expected:
        logger.error(
            "%s capture amount mismatch for payment %s: expected %s, received %s",
            gateway,
            getattr(payment, "id", None),
            expected,
            captured,
        )
        raise HTTPException(status_code=409, detail=f"{gateway} capture amount does not match the pending payment")
    return captured


def _ensure_payment_invoice(db: Session, payment: Payment, actor=None, request: Request | None = None) -> None:
    """Idempotently create (or repair) the PDF invoice for a paid gateway payment."""
    from app.schemas.invoices import InvoiceGenerateRequest
    from app.services.invoices import generate_invoice

    try:
        generate_invoice(
            db,
            InvoiceGenerateRequest(booking_id=payment.booking_id, payment_id=payment.id),
            actor,
            request,
        )
    except Exception:
        # Gateway acknowledgement must remain successful even if document
        # generation has an environmental failure. The exception is retained
        # in server logs and a repeated return/webhook repairs the invoice.
        logger.exception("Invoice generation failed for paid payment %s", payment.id)


# request schemas


class StripeSessionRequest(BaseModel):
    booking_id: int
    amount: Decimal
    currency: str = "USD"
    success_url: str
    cancel_url: str
    idempotency_key: Optional[str] = None
    # The checkout choice is recorded explicitly.  Amount remains the source
    # of truth, but this prevents a deposit selection being later described
    # as a full payment (or the reverse) in receipts and portal summaries.
    payment_type: Literal["partial", "full"]
    test_only: bool = False


class StripeReturnConfirmRequest(BaseModel):
    booking_id: int
    session_id: Optional[str] = None


class PayPalOrderRequest(BaseModel):
    booking_id: int
    amount: Decimal
    currency: str = "USD"
    return_url: str
    cancel_url: str
    idempotency_key: Optional[str] = None
    payment_type: Literal["partial", "full"]
    test_only: bool = False


class PayPalCaptureRequest(BaseModel):
    order_id: str
    # The browser normally preserves this in session storage.  It is optional
    # because a provider return can resume in a fresh browser context; the
    # order ID is already unique and ownership is checked after lookup.
    payment_id: Optional[int] = None


class PendingPaymentAbandonRequest(BaseModel):
    booking_id: int
    payment_id: Optional[int] = None


# helpers


def _ensure_booking_payment_access(booking: Booking, current_user) -> None:
    role_slug = getattr(getattr(current_user, "role", None), "slug", "") or ""
    if role_slug in {"super-admin", "admin"} or "admin" in role_slug:
        return
    if getattr(booking, "customer", None) and booking.customer.user_id == current_user.id:
        return
    if getattr(booking, "agent", None) and booking.agent.user_id == current_user.id:
        return
    raise HTTPException(status_code=403, detail="Booking access denied")


def _booking_or_404(db: Session, booking_id: int, for_update: bool = False) -> Booking:
    query = db.query(Booking).filter(Booking.id == booking_id)
    if for_update:
        query = query.with_for_update()
    b = query.first()
    if not b:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Booking not found")
    return b


def _gateway_return_urls(booking: Booking, provider: str) -> tuple[str, str]:
    """Build trusted, deployment-aware checkout return URLs server-side."""
    base = settings.FRONTEND_URL.rstrip("/")
    if booking.booking_source == "agent":
        success = f"{base}/agent/bookings/{booking.id}?payment={provider}_success"
        cancelled = f"{base}/agent/bookings/{booking.id}?payment=cancelled"
    else:
        success = f"{base}/customer/payments/success?booking_id={booking.id}&provider={provider}"
        cancelled = f"{base}/customer/payments/failed?booking_id={booking.id}&provider={provider}"
    if provider == "stripe":
        success += "&session_id={CHECKOUT_SESSION_ID}"
    return success, cancelled


def _pending_gateway_payments_total(db: Session, booking_id: int) -> Decimal:
    """Sum of payments already created for this booking whose gateway
    session/order is still pending confirmation - subtracted from the
    outstanding balance so two concurrent checkout attempts can't each
    create a full-balance session for the same booking."""
    total = (
        db.query(func.coalesce(func.sum(Payment.total_amount), 0))
        .filter(Payment.booking_id == booking_id, Payment.payment_status == "pending")
        .scalar()
    )
    return money(total or 0)


def _minimum_deposit_amount(db: Session, booking: Booking) -> Decimal:
    """The lowest amount the tour's supplier-configured deposit rule allows
    for this booking, or the full amount_pending if a deposit is no longer
    allowed (cutoff passed, or no deposit configured anywhere). Does not
    touch the balance-due-date itself -- only the deposit floor and its own
    days-before-departure cutoff, which are independent client-confirmed
    knobs (see Tour.deposit_type/deposit_percentage/deposit_cutoff_days).

    Falls back to the admin-configured default_deposit_percentage/
    default_deposit_cutoff_days settings only for whichever of those the
    tour itself hasn't set - a supplier's own per-tour values always win.

    Agent Reserve Now bookings are invoiced and paid later, so they do not
    enter this gateway deposit calculation."""
    full = money(booking.amount_pending or 0)
    tour = getattr(booking, "tour", None)

    # A customer's very first payment on this booking follows the same
    # eligibility window as the agent branch above (see
    # tour_availability.customer_deposit_eligibility / _deposit_window) --
    # the checkout page only offers "Secure with a Deposit" when this
    # returns eligible, so this must agree with that check rather than the
    # separate deposit_cutoff_days rule below, which instead governs
    # whether an *already-deposited* booking's remaining balance can still
    # be paid in installments.
    if (
        getattr(booking, "booking_source", None) != "agent"
        and money(getattr(booking, "amount_paid", 0) or 0) <= 0
        and tour is not None
        and getattr(booking, "tour_start_date", None) is not None
    ):
        from app.services.tour_availability import customer_deposit_eligibility
        eligibility = customer_deposit_eligibility(db, tour.id, booking.tour_start_date)
        if not eligibility["eligible"]:
            return full
        if eligibility["deposit_type"] == "percentage" and eligibility["deposit_percentage"]:
            return money(full * Decimal(str(eligibility["deposit_percentage"])) / Decimal("100"))
        if eligibility["booking_deposit"]:
            return money(min(Decimal(str(eligibility["booking_deposit"])), full))
        return full

    cutoff_days = getattr(tour, "deposit_cutoff_days", None) if tour else None
    if cutoff_days is None:
        cutoff_days = get_default_deposit_cutoff_days(db)
    if cutoff_days is not None and booking.tour_start_date is not None:
        days_to_departure = (as_aware_utc(booking.tour_start_date) - utcnow()).days
        if days_to_departure < cutoff_days:
            return full

    deposit_type = getattr(tour, "deposit_type", "fixed") if tour else "fixed"
    deposit_type = deposit_type or "fixed"
    pct = getattr(tour, "deposit_percentage", None) if tour else None
    fixed = getattr(tour, "booking_deposit", None) if tour else None

    if deposit_type == "percentage":
        if not pct:
            pct = get_default_deposit_percentage(db)
        if not pct:
            return full
        return money(full * Decimal(str(pct)) / Decimal("100"))

    if not fixed:
        # No fixed deposit amount configured on the tour either - fall back
        # to the platform default *percentage* rather than leaving the
        # deposit option unavailable just because "fixed" is the (default)
        # deposit_type on a tour that never touched these fields at all.
        pct = get_default_deposit_percentage(db)
        if not pct:
            return full
        return money(full * Decimal(str(pct)) / Decimal("100"))
    return money(min(Decimal(str(fixed)), full))


def _validate_payment_request(db: Session, booking: Booking, amount: Decimal, current_user, already_pending: Decimal = Decimal("0"), payment_type: str | None = None) -> Decimal:
    _ensure_booking_payment_access(booking, current_user)
    if booking.booking_status in {"cancelled", "declined", "completed", "refunded"}:
        raise HTTPException(status_code=409, detail="This booking is not eligible for payment")

    requested = money(amount)
    outstanding = money(money(booking.amount_pending or 0) - money(already_pending))
    if requested <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="This booking has no outstanding balance")
    if requested > outstanding:
        raise HTTPException(status_code=400, detail=f"Payment amount cannot exceed the outstanding balance of {outstanding:.2f}")
    inferred_type = "full" if requested == outstanding else "partial"
    if payment_type and payment_type != inferred_type:
        raise HTTPException(status_code=400, detail=f"Payment type must be {inferred_type} for the requested amount")
    # The choice made when checkout created the booking is authoritative.
    # In particular, a later change to the tour's global deposit setting must
    # not turn an older full-payment booking into a deposit-eligible one.
    if requested < outstanding and getattr(booking, "payment_type", "full") != "partial":
        raise HTTPException(status_code=400, detail="This booking was created for full payment and must be paid in full")
    if getattr(booking, "booking_source", None) == "agent" and requested < outstanding:
        raise HTTPException(status_code=400, detail="Agent bookings must be paid in full through the payment gateway")
    if requested < outstanding:
        minimum = _minimum_deposit_amount(db, booking)
        if minimum >= money(booking.amount_pending or 0):
            raise HTTPException(status_code=400, detail="A deposit is no longer available for this booking -- full payment is required")
        if requested < minimum:
            raise HTTPException(status_code=400, detail=f"Deposit must be at least {minimum:.2f}")
    return requested


@router.post("/abandon-pending")
def abandon_pending_gateway_payment(
    body: PendingPaymentAbandonRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Release a gateway checkout attempt after the customer returns via its
    cancel URL.  No funds were captured, so this must not alter the booking's
    balance; it only prevents an abandoned pending attempt from reserving the
    full amount and blocking a fresh Stripe/PayPal checkout."""
    booking = _booking_or_404(db, body.booking_id, for_update=True)
    _ensure_booking_payment_access(booking, current_user)
    query = db.query(Payment).filter(
        Payment.booking_id == booking.id,
        Payment.payment_status == "pending",
        Payment.gateway.in_(("stripe", "paypal")),
    )
    if body.payment_id is not None:
        query = query.filter(Payment.id == body.payment_id)
    payments = query.with_for_update().all()
    for payment in payments:
        payment.payment_status = "abandoned"
        payment.pending_amount = Decimal("0")
        payment.failure_reason = "Customer cancelled gateway checkout"
    db.commit()
    return {"status": "success", "message": "Pending payment attempt released", "data": {"released": len(payments)}}


def _validate_payment_currency(booking: Booking, requested_currency: str) -> str:
    booking_currency = (booking.currency or "USD").strip().upper()
    requested = (requested_currency or "").strip().upper()
    if requested != booking_currency:
        raise HTTPException(
            status_code=400,
            detail=f"Payment currency must match the booking currency ({booking_currency})",
        )
    return booking_currency


def _record_pending_payment(db: Session, booking: Booking, amount: Decimal, gateway: str, gateway_order_id: str, idempotency_key: Optional[str], current_user, payment_type: str) -> Payment:
    customer_id = booking.customer_id
    p = Payment(
        booking_id=booking.id,
        customer_id=customer_id,
        created_by=current_user.id if current_user else None,
        payment_method="card",
        payment_type=payment_type,
        gateway=gateway,
        gateway_order_id=gateway_order_id,
        idempotency_key=idempotency_key,
        total_amount=amount,
        authorized_amount=Decimal("0"),
        captured_amount=Decimal("0"),
        paid_amount=Decimal("0"),
        pending_amount=amount,
        payment_status="pending",
    )
    db.add(p)
    db.flush()
    p.payment_code = _payment_code(p.id)
    db.commit()
    db.refresh(p)
    return p


# stripe endpoints


@router.post("/stripe/create-session")
def stripe_create_session(body: StripeSessionRequest, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    check_rate_limit(request, "payment-create", max_calls=10, window_seconds=60)
    booking = _booking_or_404(db, body.booking_id, for_update=True)
    amount = _validate_payment_request(db, booking, body.amount, current_user, already_pending=_pending_gateway_payments_total(db, booking.id), payment_type=body.payment_type)
    currency = _validate_payment_currency(booking, body.currency)
    stripe = get_stripe(db)
    if body.test_only and not stripe.secret_key.startswith(("sk_test_", "rk_test_")):
        raise HTTPException(status_code=400, detail="Stripe test credentials are required")
    amount_cents = to_minor_units(amount)
    success_url, cancel_url = _gateway_return_urls(booking, "stripe")

    session_data = stripe.create_checkout_session(
        amount_cents=amount_cents,
        currency=currency,
        booking_id=body.booking_id,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=booking.customer.user.email if booking.customer and booking.customer.user else None,
        idempotency_key=body.idempotency_key,
    )

    payment = _record_pending_payment(
        db, booking, amount, "stripe",
        gateway_order_id=session_data["id"],
        idempotency_key=body.idempotency_key,
        current_user=current_user,
        payment_type=body.payment_type,
    )
    payment.gateway_payment_id = session_data.get("payment_intent")
    db.commit()

    return {
        "status": "success",
        "data": {
            "session_id": session_data["id"],
            "checkout_url": session_data.get("url"),
            "payment_id": payment.id,
        },
    }


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="", alias="stripe-signature"), db: Session = Depends(get_db)):
    from app.config import settings as app_settings
    from fastapi import HTTPException as _HTTPException

    payload = await request.body()
    webhook_secret = app_settings.STRIPE_WEBHOOK_SECRET.strip()

    if webhook_secret:
        stripe_gw = get_stripe(db)
        event = stripe_gw.construct_event(payload, stripe_signature, webhook_secret)
    elif app_settings.is_production:
        logger.critical("Stripe webhook received without STRIPE_WEBHOOK_SECRET -- rejecting in production")
        raise _HTTPException(status_code=400, detail="Webhook signature verification not configured")
    else:
        logger.warning("Stripe webhook received without signature verification (dev mode)")
        try:
            event = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise _HTTPException(status_code=400, detail="Invalid Stripe webhook payload") from error

    if not isinstance(event, dict):
        raise _HTTPException(status_code=400, detail="Invalid Stripe webhook payload")

    event_id = event.get("id", "")
    event_type = event.get("type", "")
    logger.info("Stripe webhook received: %s id=%s", event_type, event_id)

    # Idempotency: skip events already recorded via their Stripe event ID
    existing_transaction = db.query(PaymentTransaction).filter(PaymentTransaction.gateway_reference == event_id).first() if event_id else None
    if existing_transaction:
        logger.info("Stripe event %s already processed -- skipping", event_id)
        payment = db.query(Payment).filter(Payment.id == existing_transaction.payment_id).first()
        if payment and payment.payment_status == "paid":
            _ensure_payment_invoice(db, payment, request=request)
        return {"status": "success", "received": True}

    if event_type == "checkout.session.completed":
        session_obj = event["data"]["object"]
        order_id = session_obj.get("id")
        payment_intent = session_obj.get("payment_intent")
        payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            # Development can accept an unsigned webhook, where ``stripe_gw``
            # was not created in the signature-verification branch.
            intent = get_stripe(db).retrieve_payment_intent(payment_intent)
            if intent.get("status") == "requires_capture":
                capture_before = intent.get("charges", {}).get("data", [{}])[0].get("payment_method_details", {}).get("card", {}).get("capture_before")
                expires_at = datetime.fromtimestamp(capture_before, tz=timezone.utc) if capture_before else None
                record_gateway_authorization(db, payment, gateway_reference=payment_intent, expires_at=expires_at)

    elif event_type in ("payment_intent.payment_failed", "checkout.session.expired"):
        obj = event["data"]["object"]
        order_id = obj.get("id")
        payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            payment.payment_status = "failed"
            payment.failure_reason = obj.get("last_payment_error", {}).get("message", "Payment failed") if event_type == "payment_intent.payment_failed" else "Session expired"
            db.commit()
            from app.services.payments import notify_payment_failed
            notify_payment_failed(db, payment, payment.failure_reason or "Payment failed")

    elif event_type == "charge.refunded":
        charge = event["data"]["object"]
        payment_intent = charge.get("payment_intent")
        refund_amount = money(Decimal(charge.get("amount_refunded", 0)) / 100)
        payment = db.query(Payment).filter(Payment.gateway_payment_id == payment_intent).first()
        if payment:
            payment.refunded_amount = refund_amount
            payment.payment_status = "refunded" if refund_amount >= payment.captured_amount else "partially_refunded"
            if payment.booking:
                _sync_booking_payment_fields(db, payment.booking)
            db.commit()

    return {"status": "success", "received": True}


# paypal endpoints



@router.post("/stripe/confirm-return")
def stripe_confirm_return(body: StripeReturnConfirmRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    booking = _booking_or_404(db, body.booking_id)
    _ensure_booking_payment_access(booking, current_user)

    payment = None
    session_obj = None

    if body.session_id:
        stripe = get_stripe(db)
        session_obj = stripe.retrieve_session(body.session_id)
        if session_obj.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Stripe session is not complete yet")
        payment = db.query(Payment).filter(
            Payment.gateway == "stripe",
            Payment.gateway_order_id == body.session_id,
            Payment.booking_id == booking.id,
        ).order_by(Payment.id.desc()).first()
    elif not settings.is_production:
        payment = db.query(Payment).filter(
            Payment.gateway == "stripe",
            Payment.booking_id == booking.id,
            Payment.payment_status == "pending",
        ).order_by(Payment.id.desc()).first()
    else:
        raise HTTPException(status_code=400, detail="Stripe session_id is required")

    if not payment:
        raise HTTPException(status_code=404, detail="Pending Stripe payment not found")

    if payment.payment_status == "pending":
        if not session_obj:
            raise HTTPException(status_code=400, detail="Stripe session_id is required")
        _require_captured_amount_matches_pending(payment, money(Decimal(session_obj.get("amount_total", 0)) / 100), "Stripe")
        intent_id = session_obj.get("payment_intent")
        intent = stripe.retrieve_payment_intent(intent_id)
        if intent.get("status") != "requires_capture":
            raise HTTPException(status_code=400, detail="Stripe payment is not authorized for capture")
        capture_before = intent.get("charges", {}).get("data", [{}])[0].get("payment_method_details", {}).get("card", {}).get("capture_before")
        expires_at = datetime.fromtimestamp(capture_before, tz=timezone.utc) if capture_before else None
        record_gateway_authorization(db, payment, gateway_reference=intent_id, expires_at=expires_at, actor=current_user)

    return {
        "status": "success",
        "message": "Stripe payment authorized; it will be captured only after supplier acceptance",
        "data": {"payment_id": payment.id, "booking_id": booking.id, "payment_status": payment.payment_status},
    }

@router.post("/paypal/create-order")
def paypal_create_order(body: PayPalOrderRequest, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    check_rate_limit(request, "payment-create", max_calls=10, window_seconds=60)
    booking = _booking_or_404(db, body.booking_id, for_update=True)
    amount = _validate_payment_request(db, booking, body.amount, current_user, already_pending=_pending_gateway_payments_total(db, booking.id), payment_type=body.payment_type)
    currency = _validate_payment_currency(booking, body.currency)
    paypal = get_paypal(db)
    if getattr(body, "test_only", False) and "sandbox" not in paypal.base_url:
        raise HTTPException(status_code=400, detail="PayPal sandbox credentials are required")
    amount_str = f"{amount:.2f}"
    return_url, cancel_url = _gateway_return_urls(booking, "paypal")

    order = paypal.create_order(
        amount=amount_str,
        currency=currency,
        booking_id=body.booking_id,
        return_url=return_url,
        cancel_url=cancel_url,
        idempotency_key=body.idempotency_key,
    )

    payment = _record_pending_payment(
        db, booking, amount, "paypal",
        gateway_order_id=order["id"],
        idempotency_key=body.idempotency_key,
        current_user=current_user,
        payment_type=body.payment_type,
    )

    approve_link = next((l["href"] for l in order.get("links", []) if l.get("rel") == "approve"), None)

    return {
        "status": "success",
        "data": {
            "order_id": order["id"],
            "approve_url": approve_link,
            "payment_id": payment.id,
        },
    }


@router.post("/paypal/capture")
def paypal_capture(body: PayPalCaptureRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    query = db.query(Payment).filter(
        Payment.gateway == "paypal",
        Payment.gateway_order_id == body.order_id,
    )
    if body.payment_id is not None:
        query = query.filter(Payment.id == body.payment_id)
    payment = query.with_for_update().first()
    if not payment:
        raise HTTPException(status_code=404, detail="PayPal payment record not found")
    _ensure_booking_payment_access(payment.booking, current_user)
    if payment.payment_status == "paid":
        _ensure_payment_invoice(db, payment, actor=current_user)
        return {"status": "success", "message": "PayPal payment was already captured", "data": {"paypal_status": "COMPLETED", "payment_id": payment.id}}
    if payment.payment_status == "authorized":
        return {"status": "success", "message": "PayPal payment is already authorized", "data": {"paypal_status": "COMPLETED", "payment_id": payment.id}}

    paypal = get_paypal(db)
    captured = paypal.authorize_order(order_id=body.order_id, idempotency_key=f"authorize:{payment.id}")

    status = captured.get("status", "")
    if status == "COMPLETED":
        units = captured.get("purchase_units", [{}])
        authorizations = units[0].get("payments", {}).get("authorizations", [{}])
        authorization = authorizations[0] if authorizations else {}
        authorized_amt = _require_captured_amount_matches_pending(
            payment,
            _require_paypal_amount(authorization.get("amount", {}), "authorization"),
            "PayPal",
        )
        if authorized_amt != money(payment.total_amount):
            raise HTTPException(status_code=409, detail="PayPal authorization amount does not match the pending payment")
        expiration = authorization.get("expiration_time")
        expires_at = datetime.fromisoformat(expiration.replace("Z", "+00:00")) if expiration else None
        record_gateway_authorization(db, payment, gateway_reference=authorization.get("id", ""), expires_at=expires_at, actor=current_user)

    return {"status": "success", "message": f"PayPal authorization status: {status}; capture follows supplier acceptance", "data": {"paypal_status": status, "payment_id": payment.id}}


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    from app.config import settings as app_settings
    from app.services.payments_gateway import _load_setting
    from fastapi import HTTPException as _HTTPException

    payload = await request.body()
    try:
        event = json.loads(payload)
    except Exception:
        raise _HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(event, dict):
        raise _HTTPException(status_code=400, detail="Invalid PayPal webhook payload")

    setting = _load_setting(db, "paypal")
    webhook_id = (setting.webhook_id if setting else "") or ""

    if webhook_id:
        paypal_gw = get_paypal(db)
        verified = paypal_gw.verify_webhook_signature(headers=request.headers, webhook_id=webhook_id, event_body=event)
        if not verified:
            logger.error("PayPal webhook signature verification failed")
            raise _HTTPException(status_code=400, detail="Webhook signature verification failed")
    elif app_settings.is_production:
        logger.critical("PayPal webhook received without a configured webhook_id -- rejecting in production")
        raise _HTTPException(status_code=400, detail="Webhook signature verification not configured")
    else:
        logger.warning("PayPal webhook received without signature verification (dev mode)")

    event_id = event.get("id", "")
    event_type = event.get("event_type", "")
    logger.info("PayPal webhook received: %s id=%s", event_type, event_id)

    # Idempotency: skip events already recorded via PayPal event ID
    existing_transaction = db.query(PaymentTransaction).filter(PaymentTransaction.gateway_reference == event_id).first() if event_id else None
    if existing_transaction:
        logger.info("PayPal event %s already processed -- skipping", event_id)
        payment = db.query(Payment).filter(Payment.id == existing_transaction.payment_id).first()
        if payment and payment.payment_status == "paid":
            _ensure_payment_invoice(db, payment, request=request)
        return {"status": "success", "received": True}

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event.get("resource", {})
        capture_id = resource.get("id")
        order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        captured_amt = _require_paypal_amount(resource.get("amount", {}), "PAYMENT.CAPTURE.COMPLETED")

        payment = None
        if order_id:
            payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            captured_amt = _require_captured_amount_matches_pending(payment, captured_amt, "PayPal")
            payment.captured_amount = captured_amt
            payment.paid_amount = captured_amt
            payment.pending_amount = Decimal("0")
            payment.payment_status = "paid"
            payment.gateway_payment_id = capture_id
            db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type="capture", amount=captured_amt, status="success", gateway_reference=event_id or capture_id, metadata_json={"event_type": event_type, "capture_id": capture_id}))
            _sync_booking_payment_fields(db, payment.booking)
            db.commit()
            _ensure_payment_invoice(db, payment, request=request)

    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        resource = event.get("resource", {})
        refunded_amt = _require_paypal_amount(resource.get("amount", {}), "PAYMENT.CAPTURE.REFUNDED")
        links = resource.get("links", [])
        capture_href = next((l["href"] for l in links if l.get("rel") == "up"), "")
        capture_id = capture_href.rstrip("/").split("/")[-1] if capture_href else None

        if capture_id:
            payment = db.query(Payment).filter(Payment.gateway_payment_id == capture_id).first()
            if payment:
                # Unlike Stripe's charge.amount_refunded (a running total),
                # PAYMENT.CAPTURE.REFUNDED's resource.amount is only the
                # amount of THIS refund - it must be added to what's already
                # recorded, or a second partial refund would overwrite and
                # lose the first.
                payment.refunded_amount = money(payment.refunded_amount) + refunded_amt
                payment.payment_status = "refunded" if payment.refunded_amount >= payment.captured_amount else "partially_refunded"
                if payment.booking:
                    _sync_booking_payment_fields(db, payment.booking)
                db.commit()

    return {"status": "success", "received": True}


# gateway status probe  (get /payments/gateways/status)


@router.get("/gateways/status")
def gateways_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Returns which gateways are configured so the frontend can adapt the payment modal."""
    from app.services.payments_gateway import _load_setting
    stripe_ok = False
    paypal_ok = False
    stripe_test = False
    paypal_test = False
    try:
        s = _load_setting(db, "stripe")
        stripe_ok = bool(s and s.secret_key)
        if stripe_ok:
            from app.utils.crypto import decrypt_secret
            stripe_test = decrypt_secret(s.secret_key).startswith(("sk_test_", "rk_test_"))
    except Exception:
        pass
    try:
        p = _load_setting(db, "paypal")
        paypal_ok = bool(p and p.public_key and p.secret_key)
        from app.services.payments_gateway import normalize_paypal_mode
        paypal_test = paypal_ok and normalize_paypal_mode(getattr(p, "mode", "sandbox")) == "sandbox"
    except Exception:
        pass
    return {
        "status": "success",
        "data": {
            "stripe_test": stripe_test,
            "paypal_test": paypal_test,
            "stripe": stripe_ok,
            "paypal": paypal_ok,
            "test_mode_available": not settings.is_production,
        },
    }


# test / simulate payment  (post /payments/test/simulate)


class TestPaymentRequest(BaseModel):
    booking_id: int
    amount: Decimal
    note: Optional[str] = "Test payment"


@router.post("/test/simulate")
def test_simulate_payment(
    body: TestPaymentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Simulate a successful payment without calling any real gateway. Non-production only."""
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Test payments are not available in production.")

    booking = _booking_or_404(db, body.booking_id)
    amount = _validate_payment_request(db, booking, body.amount, current_user)
    fake_ref = f"TEST-{uuid.uuid4().hex[:10].upper()}"

    payment = Payment(
        booking_id=booking.id,
        customer_id=booking.customer_id,
        created_by=current_user.id if current_user else None,
        payment_method="test",
        payment_type="partial" if amount < money(booking.amount_pending or 0) else "full",
        gateway="test",
        gateway_order_id=fake_ref,
        idempotency_key=fake_ref,
        total_amount=amount,
        authorized_amount=amount,
        captured_amount=amount,
        paid_amount=amount,
        pending_amount=Decimal("0"),
        payment_status="paid",
    )
    db.add(payment)
    db.flush()
    payment.payment_code = _payment_code(payment.id)
    db.add(
        PaymentTransaction(
            payment_id=payment.id,
            booking_id=payment.booking_id,
            transaction_type="capture",
            amount=amount,
            status="success",
            gateway_reference=fake_ref,
            metadata_json={"test_mode": True, "note": body.note},
        )
    )
    _sync_booking_payment_fields(db, payment.booking)
    db.commit()
    db.refresh(payment)
    _ensure_payment_invoice(db, payment, actor=current_user)

    return {
        "status": "success",
        "data": {
            "payment_id": payment.id,
            "payment_code": payment.payment_code,
            "gateway_reference": fake_ref,
        },
    }
