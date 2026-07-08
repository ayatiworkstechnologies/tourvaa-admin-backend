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
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.modules.bookings.models import Booking
from app.modules.common.auth import get_current_user
from app.modules.common.money import money, utcnow
from app.modules.payments.gateway import get_paypal, get_stripe
from app.modules.payments.models import Payment, PaymentTransaction
from app.modules.payments.service import _payment_code, _sync_booking_payment_fields

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payment Gateways"])


# request schemas


class StripeSessionRequest(BaseModel):
    booking_id: int
    amount: Decimal
    currency: str = "USD"
    success_url: str
    cancel_url: str
    idempotency_key: Optional[str] = None


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


class PayPalCaptureRequest(BaseModel):
    order_id: str
    payment_id: int


# helpers


def _ensure_booking_payment_access(booking: Booking, current_user) -> None:
    role_slug = getattr(getattr(current_user, "role", None), "slug", "") or ""
    if role_slug in {"super-admin", "admin"} or "admin" in role_slug:
        return
    if booking.customer and booking.customer.user_id == current_user.id:
        return
    raise HTTPException(status_code=403, detail="Booking access denied")


def _booking_or_404(db: Session, booking_id: int) -> Booking:
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Booking not found")
    return b


def _record_pending_payment(db: Session, booking: Booking, amount: Decimal, gateway: str, gateway_order_id: str, idempotency_key: Optional[str], current_user) -> Payment:
    customer_id = booking.customer_id
    p = Payment(
        booking_id=booking.id,
        customer_id=customer_id,
        created_by=current_user.id if current_user else None,
        payment_method="card",
        payment_type="full",
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
def stripe_create_session(body: StripeSessionRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    stripe = get_stripe(db)
    booking = _booking_or_404(db, body.booking_id)
    amount_cents = int(money(body.amount) * 100)

    session_data = stripe.create_checkout_session(
        amount_cents=amount_cents,
        currency=body.currency,
        booking_id=body.booking_id,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        customer_email=booking.customer.user.email if booking.customer and booking.customer.user else None,
        idempotency_key=body.idempotency_key,
    )

    payment = _record_pending_payment(
        db, booking, body.amount, "stripe",
        gateway_order_id=session_data["id"],
        idempotency_key=body.idempotency_key,
        current_user=current_user,
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
    elif app_settings.APP_ENV == "production":
        logger.critical("Stripe webhook received without STRIPE_WEBHOOK_SECRET -- rejecting in production")
        raise _HTTPException(status_code=400, detail="Webhook signature verification not configured")
    else:
        logger.warning("Stripe webhook received without signature verification (dev mode)")
        event = json.loads(payload)

    event_id = event.get("id", "")
    event_type = event.get("type", "")
    logger.info("Stripe webhook received: %s id=%s", event_type, event_id)

    # Idempotency: skip events already recorded via their Stripe event ID
    if event_id and db.query(PaymentTransaction).filter(PaymentTransaction.gateway_reference == event_id).first():
        logger.info("Stripe event %s already processed -- skipping", event_id)
        return {"status": "success", "received": True}

    if event_type == "checkout.session.completed":
        session_obj = event["data"]["object"]
        order_id = session_obj.get("id")
        payment_intent = session_obj.get("payment_intent")
        amount_total = session_obj.get("amount_total", 0)

        payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            captured_amt = money(Decimal(amount_total) / 100)
            payment.captured_amount = captured_amt
            payment.paid_amount = captured_amt
            payment.pending_amount = Decimal("0")
            payment.payment_status = "paid"
            payment.gateway_payment_id = payment_intent
            db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type="capture", amount=captured_amt, status="success", gateway_reference=event_id or payment_intent, metadata_json={"event": event_type}))
            _sync_booking_payment_fields(db, payment.booking)
            db.commit()

    elif event_type in ("payment_intent.payment_failed", "checkout.session.expired"):
        obj = event["data"]["object"]
        order_id = obj.get("id")
        payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            payment.payment_status = "failed"
            payment.failure_reason = obj.get("last_payment_error", {}).get("message", "Payment failed") if event_type == "payment_intent.payment_failed" else "Session expired"
            db.commit()

    elif event_type == "charge.refunded":
        charge = event["data"]["object"]
        payment_intent = charge.get("payment_intent")
        refund_amount = money(Decimal(charge.get("amount_refunded", 0)) / 100)
        payment = db.query(Payment).filter(Payment.gateway_payment_id == payment_intent).first()
        if payment:
            payment.refunded_amount = refund_amount
            payment.payment_status = "refunded" if refund_amount >= payment.captured_amount else "partially_refunded"
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
        if session_obj.get("payment_status") != "paid" and session_obj.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Stripe session is not paid yet")
        payment = db.query(Payment).filter(
            Payment.gateway == "stripe",
            Payment.gateway_order_id == body.session_id,
            Payment.booking_id == booking.id,
        ).order_by(Payment.id.desc()).first()
    elif settings.APP_ENV != "production":
        payment = db.query(Payment).filter(
            Payment.gateway == "stripe",
            Payment.booking_id == booking.id,
            Payment.payment_status == "pending",
        ).order_by(Payment.id.desc()).first()
    else:
        raise HTTPException(status_code=400, detail="Stripe session_id is required")

    if not payment:
        raise HTTPException(status_code=404, detail="Pending Stripe payment not found")

    if payment.payment_status != "paid":
        captured_amt = money(payment.total_amount or booking.amount_pending or booking.final_amount or 0)
        payment.captured_amount = captured_amt
        payment.paid_amount = captured_amt
        payment.pending_amount = Decimal("0")
        payment.payment_status = "paid"
        if session_obj:
            payment.gateway_payment_id = session_obj.get("payment_intent") or payment.gateway_payment_id
        ref = body.session_id or f"STRIPE-RETURN-{payment.id}"
        existing_txn = db.query(PaymentTransaction).filter(
            PaymentTransaction.payment_id == payment.id,
            PaymentTransaction.gateway_reference == ref,
        ).first()
        if not existing_txn:
            db.add(PaymentTransaction(
                payment_id=payment.id,
                booking_id=payment.booking_id,
                transaction_type="capture",
                amount=captured_amt,
                status="success",
                gateway_reference=ref,
                metadata_json={"source": "stripe_return", "verified": bool(body.session_id)},
                created_by=current_user.id if current_user else None,
            ))
        _sync_booking_payment_fields(db, payment.booking)
        db.commit()
        db.refresh(payment)

    return {
        "status": "success",
        "message": "Stripe payment confirmed",
        "data": {"payment_id": payment.id, "booking_id": booking.id, "payment_status": payment.payment_status},
    }

@router.post("/paypal/create-order")
def paypal_create_order(body: PayPalOrderRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    paypal = get_paypal(db)
    booking = _booking_or_404(db, body.booking_id)
    amount_str = f"{money(body.amount):.2f}"

    order = paypal.create_order(
        amount=amount_str,
        currency=body.currency,
        booking_id=body.booking_id,
        return_url=body.return_url,
        cancel_url=body.cancel_url,
        idempotency_key=body.idempotency_key,
    )

    payment = _record_pending_payment(
        db, booking, body.amount, "paypal",
        gateway_order_id=order["id"],
        idempotency_key=body.idempotency_key,
        current_user=current_user,
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
    paypal = get_paypal(db)
    captured = paypal.capture_order(order_id=body.order_id)

    payment = db.query(Payment).filter(Payment.id == body.payment_id).first()
    if not payment:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Payment record not found")

    status = captured.get("status", "")
    if status == "COMPLETED":
        units = captured.get("purchase_units", [{}])
        captures = units[0].get("payments", {}).get("captures", [{}])
        capture_obj = captures[0] if captures else {}
        amount_value = capture_obj.get("amount", {}).get("value", "0")
        captured_amt = money(Decimal(amount_value))
        capture_id = capture_obj.get("id", "")

        payment.captured_amount = captured_amt
        payment.paid_amount = captured_amt
        payment.pending_amount = Decimal("0")
        payment.payment_status = "paid"
        payment.gateway_payment_id = capture_id
        db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type="capture", amount=captured_amt, status="success", gateway_reference=capture_id, metadata_json={"paypal_order_id": body.order_id}))
        _sync_booking_payment_fields(db, payment.booking)
        db.commit()
        db.refresh(payment)

    return {"status": "success", "message": f"PayPal capture status: {status}", "data": {"paypal_status": status, "payment_id": payment.id}}


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    from fastapi import HTTPException as _HTTPException

    payload = await request.body()
    try:
        event = json.loads(payload)
    except Exception:
        raise _HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = event.get("id", "")
    event_type = event.get("event_type", "")
    logger.info("PayPal webhook received: %s id=%s", event_type, event_id)

    # Idempotency: skip events already recorded via PayPal event ID
    if event_id and db.query(PaymentTransaction).filter(PaymentTransaction.gateway_reference == event_id).first():
        logger.info("PayPal event %s already processed -- skipping", event_id)
        return {"status": "success", "received": True}

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event.get("resource", {})
        capture_id = resource.get("id")
        order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        amount_value = resource.get("amount", {}).get("value", "0")
        captured_amt = money(Decimal(amount_value))

        payment = None
        if order_id:
            payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            payment.captured_amount = captured_amt
            payment.paid_amount = captured_amt
            payment.pending_amount = Decimal("0")
            payment.payment_status = "paid"
            payment.gateway_payment_id = capture_id
            db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type="capture", amount=captured_amt, status="success", gateway_reference=event_id or capture_id, metadata_json={"event_type": event_type, "capture_id": capture_id}))
            _sync_booking_payment_fields(db, payment.booking)
            db.commit()

    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        resource = event.get("resource", {})
        amount_value = resource.get("amount", {}).get("value", "0")
        refunded_amt = money(Decimal(amount_value))
        links = resource.get("links", [])
        capture_href = next((l["href"] for l in links if l.get("rel") == "up"), "")
        capture_id = capture_href.rstrip("/").split("/")[-1] if capture_href else None

        if capture_id:
            payment = db.query(Payment).filter(Payment.gateway_payment_id == capture_id).first()
            if payment:
                payment.refunded_amount = refunded_amt
                payment.payment_status = "refunded" if refunded_amt >= payment.captured_amount else "partially_refunded"
                db.commit()

    return {"status": "success", "received": True}


# gateway status probe  (get /payments/gateways/status)


@router.get("/gateways/status")
def gateways_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Returns which gateways are configured so the frontend can adapt the payment modal."""
    from app.modules.payments.gateway import _load_setting
    stripe_ok = False
    paypal_ok = False
    try:
        s = _load_setting(db, "stripe")
        stripe_ok = bool(s and s.secret_key)
    except Exception:
        pass
    try:
        p = _load_setting(db, "paypal")
        paypal_ok = bool(p and p.public_key and p.secret_key)
    except Exception:
        pass
    return {
        "status": "success",
        "data": {
            "stripe": stripe_ok,
            "paypal": paypal_ok,
            "test_mode_available": settings.APP_ENV != "production",
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
    if settings.APP_ENV == "production":
        raise HTTPException(status_code=403, detail="Test payments are not available in production.")

    booking = _booking_or_404(db, body.booking_id)
    amount = money(body.amount)
    fake_ref = f"TEST-{uuid.uuid4().hex[:10].upper()}"

    payment = Payment(
        booking_id=booking.id,
        customer_id=booking.customer_id,
        created_by=current_user.id if current_user else None,
        payment_method="test",
        payment_type="full",
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

    return {
        "status": "success",
        "data": {
            "payment_id": payment.id,
            "payment_code": payment.payment_code,
            "gateway_reference": fake_ref,
        },
    }
