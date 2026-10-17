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
