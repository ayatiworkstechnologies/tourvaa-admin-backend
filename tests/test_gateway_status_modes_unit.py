from types import SimpleNamespace

import pytest

from app.routers.payments_gateway import gateways_status


@pytest.mark.parametrize("key, enabled, test_mode", [
    ("sk_test_example", True, True),
    ("sk_live_example", True, False),
    ("invalid", False, False),
])
def test_gateway_status_distinguishes_live_and_test(monkeypatch, key, enabled, test_mode):
    monkeypatch.setattr("app.services.payments_gateway._load_setting", lambda db, provider: SimpleNamespace(secret_key="encrypted") if provider == "stripe" else None)
    monkeypatch.setattr("app.utils.crypto.decrypt_secret", lambda value: key)
    data = gateways_status(db=None, current_user=None)["data"]
    assert data["stripe"] is enabled
    assert data["stripe_test"] is test_mode


def test_unreadable_key_does_not_enable_gateway(monkeypatch):
    monkeypatch.setattr("app.services.payments_gateway._load_setting", lambda db, provider: SimpleNamespace(secret_key="encrypted") if provider == "stripe" else None)
    def fail(value):
        raise ValueError("Cannot decrypt")
    monkeypatch.setattr("app.utils.crypto.decrypt_secret", fail)
    data = gateways_status(db=None, current_user=None)["data"]
    assert data["stripe"] is False
    assert data["stripe_test"] is False


@pytest.mark.parametrize(("mode", "test_mode"), [("live", False), ("sandbox", True)])
def test_gateway_status_uses_mode_specific_paypal_credentials(monkeypatch, mode, test_mode):
    def configured_gateway(_db, provider):
        if provider != "paypal":
            return None
        return SimpleNamespace(
            mode=mode,
            public_key=None,
            secret_key=None,
            live_client_id="live-client-id",
            live_secret="encrypted-live-secret",
            sandbox_client_id="sandbox-client-id",
            sandbox_secret="encrypted-sandbox-secret",
        )

    monkeypatch.setattr("app.services.payments_gateway._load_setting", configured_gateway)

    data = gateways_status(db=None, current_user=None)["data"]

    assert data["paypal"] is True
    assert data["paypal_test"] is test_mode
