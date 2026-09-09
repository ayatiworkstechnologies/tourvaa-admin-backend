from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from app.routers import payments_gateway as routes


@pytest.mark.parametrize("provider", ["stripe", "paypal"])
def test_test_checkout_rejects_live_gateway_before_network(monkeypatch, provider):
    monkeypatch.setattr(routes, "check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(routes, "_booking_or_404", lambda *a, **k: SimpleNamespace(id=1))
    monkeypatch.setattr(routes, "_pending_gateway_payments_total", lambda *a: 0)
    monkeypatch.setattr(routes, "_validate_payment_request", lambda *a, **k: 10)
    monkeypatch.setattr(routes, "_validate_payment_currency", lambda *a: "USD")
    gateway = Mock(secret_key="sk_live_example", base_url="https://api-m.paypal.com")
    monkeypatch.setattr(routes, f"get_{provider}", lambda db: gateway)
    common = dict(booking_id=1, amount=10, test_only=True, cancel_url="https://example.com/cancel")
    body = (routes.StripeSessionRequest(**common, success_url="https://example.com/success")
            if provider == "stripe" else routes.PayPalOrderRequest(**common, return_url="https://example.com/success"))
    endpoint = routes.stripe_create_session if provider == "stripe" else routes.paypal_create_order
    with pytest.raises(HTTPException) as exc:
        endpoint(body, request=Mock(), db=Mock(), current_user=Mock())
    assert exc.value.status_code == 400
    gateway.create_checkout_session.assert_not_called()
    gateway.create_order.assert_not_called()
