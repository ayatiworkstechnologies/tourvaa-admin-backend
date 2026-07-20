from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services import currency


def rate_payload():
    return {
        "base": "USD",
        "rates": {"USD": Decimal("1"), "EUR": Decimal("0.8"), "INR": Decimal("80")},
        "source": "test",
        "rate_date": "2026-07-20",
        "is_stale": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc),
    }


def test_cross_currency_conversion_uses_usd_cross_rates(monkeypatch):
    monkeypatch.setattr(currency, "get_usd_rates", rate_payload)
    converted, rate, _ = currency.convert_amount(Decimal("100"), "EUR", "INR")
    assert rate == Decimal("100")
    assert converted == Decimal("10000.00")


def test_rate_table_can_be_rebased(monkeypatch):
    monkeypatch.setattr(currency, "get_usd_rates", rate_payload)
    result = currency.rates_for("EUR")
    assert result["base"] == "EUR"
    assert result["rates"]["USD"] == pytest.approx(1.25)


def test_unsupported_currency_is_rejected(monkeypatch):
    monkeypatch.setattr(currency, "get_usd_rates", rate_payload)
    with pytest.raises(ValueError):
        currency.convert_amount(Decimal("10"), "XYZ", "USD")
