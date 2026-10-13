from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services import settings
from app.services.payments_gateway import PayPalGateway, normalize_paypal_mode


def _db_with(payment_setting):
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = payment_setting
    return db


def test_stripe_connection_success_is_persisted(monkeypatch):
    row = SimpleNamespace(
        id=1,
        provider_name="stripe",
        secret_key="encrypted",
        last_test_status=None,
        last_test_at=None,
        last_test_error=None,
    )
    db = _db_with(row)
    response = Mock(status_code=200)
    monkeypatch.setattr(settings, "decrypt_secret", lambda value: "sk_test_valid")
    monkeypatch.setattr("requests.get", Mock(return_value=response))
    monkeypatch.setattr(settings, "log_audit", Mock())

    result = settings.test_payment_connection(db, "stripe")

    assert result["connected"] is True
    assert result["mode"] == "test"
    assert result["error"] is None
    assert row.last_test_status == "connected"
    assert row.last_test_error is None
    assert db.commit.call_count == 2


def test_paypal_auth_failure_is_safe_and_persisted(monkeypatch):
    row = SimpleNamespace(
        id=2,
        provider_name="paypal",
        public_key="client-id",
        secret_key="encrypted",
        mode="sandbox",
        last_test_status=None,
        last_test_at=None,
        last_test_error=None,
    )
    db = _db_with(row)
    response = Mock(status_code=401)
    monkeypatch.setattr(settings, "decrypt_secret", lambda value: "client-secret")
    monkeypatch.setattr("requests.post", Mock(return_value=response))
    monkeypatch.setattr(settings, "log_audit", Mock())

    result = settings.test_payment_connection(db, "paypal")

    assert result["connected"] is False
    assert result["mode"] == "sandbox"
    assert "invalid PayPal" in result["error"]
    assert row.last_test_status == "failed"
    assert row.last_test_error == result["error"]


def test_unknown_payment_provider_is_rejected_without_network():
    with pytest.raises(HTTPException) as error:
        settings.test_payment_connection(Mock(), "unknown")

    assert error.value.status_code == 404


@pytest.mark.parametrize(
    ("configured", "normalized", "base_url"),
    [
        ("sandbox", "sandbox", "https://api-m.sandbox.paypal.com"),
        ("TEST", "sandbox", "https://api-m.sandbox.paypal.com"),
        ("LIVE", "live", "https://api-m.paypal.com"),
    ],
)
def test_paypal_mode_is_normalized_before_selecting_an_api_host(configured, normalized, base_url):
    gateway = PayPalGateway("client", "secret", configured)

    assert normalize_paypal_mode(configured) == normalized
    assert gateway.mode == normalized
    assert gateway.base_url == base_url


def test_paypal_mode_rejects_an_unknown_value():
    with pytest.raises(ValueError, match="sandbox.*live"):
        normalize_paypal_mode("production")
