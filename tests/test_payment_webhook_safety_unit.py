"""Pure unit coverage for the payment webhook safety boundaries.

These tests deliberately do not contact a gateway or the local application DB.
"""

import hashlib
import hmac
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.payments_gateway import (
    _require_captured_amount_matches_pending,
    _require_payment_currency,
)
from app.services.payments_gateway import StripeGateway


def _payment(amount="42.50", currency="USD"):
    return SimpleNamespace(id=7, total_amount=amount, booking=SimpleNamespace(currency=currency))


def test_signed_stripe_payload_verifies_and_tampering_is_rejected():
    secret = "whsec_unit_test"
    body = b'{"id":"evt_1","type":"checkout.session.completed"}'
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), f"{timestamp}.{body.decode()}".encode(), hashlib.sha256).hexdigest()

    assert StripeGateway("sk_test_unit").construct_event(body, f"t={timestamp},v1={signature}", secret)["id"] == "evt_1"
    with pytest.raises(HTTPException, match="signature invalid"):
        StripeGateway("sk_test_unit").construct_event(body + b" ", f"t={timestamp},v1={signature}", secret)


def test_webhook_amount_and_currency_must_match_the_payment_attempt():
    payment = _payment()
    assert _require_captured_amount_matches_pending(payment, "42.50", "Stripe") == Decimal("42.50")
    _require_payment_currency(payment, "usd", "Stripe")

    with pytest.raises(HTTPException, match="amount does not match"):
        _require_captured_amount_matches_pending(payment, "42.49", "Stripe")
    with pytest.raises(HTTPException, match="currency does not match"):
        _require_payment_currency(payment, "EUR", "Stripe")
