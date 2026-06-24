"""
Gateway-specific payment routes:
  POST /payments/stripe/create-session
  POST /payments/stripe/webhook
  POST /payments/paypal/create-order
  POST /payments/paypal/capture
  POST /payments/paypal/webhook
"""

import json
import logging
from decimal import Decimal
from typing import Optional

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
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


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class StripeSessionRequest(BaseModel):
    booking_id: int
    amount: Decimal
    currency: str = "USD"
    success_url: str
    cancel_url: str
    idempotency_key: Optional[str] = None


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Stripe endpoints
# ---------------------------------------------------------------------------


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
    from app.modules.settings.models import PaymentSetting

    setting = db.query(PaymentSetting).filter(PaymentSetting.provider_name == "stripe").first()
    webhook_secret = getattr(setting, "webhook_secret", None) if setting else None

    payload = await request.body()

    if webhook_secret:
        stripe = get_stripe(db)
        event = stripe.construct_event(payload, stripe_signature, webhook_secret)
    else:
        event = json.loads(payload)

    event_type = event.get("type", "")
    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        session_obj = event["data"]["object"]
        order_id = session_obj.get("id")
        payment_intent = session_obj.get("payment_intent")
        amount_total = session_obj.get("amount_total", 0)
        booking_id = int(session_obj.get("metadata", {}).get("booking_id", 0))

        payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
        if payment and payment.payment_status == "pending":
            captured_amt = money(Decimal(amount_total) / 100)
            payment.captured_amount = captured_amt
            payment.paid_amount = captured_amt
            payment.pending_amount = Decimal("0")
            payment.payment_status = "paid"
            payment.gateway_payment_id = payment_intent
            db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type="capture", amount=captured_amt, status="success", gateway_reference=payment_intent, metadata_json={"event": event_type}))
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


# ---------------------------------------------------------------------------
# PayPal endpoints
# ---------------------------------------------------------------------------


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
    payload = await request.body()
    try:
        event = json.loads(payload)
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("event_type", "")
    logger.info("PayPal webhook received: %s", event_type)

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
            db.add(PaymentTransaction(payment_id=payment.id, booking_id=payment.booking_id, transaction_type="capture", amount=captured_amt, status="success", gateway_reference=capture_id, metadata_json={"event_type": event_type}))
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
