"""Display-currency conversion using USD as the platform accounting base.

Bookings retain the tour/transaction currency that was priced by the server.
These rates are for browsing and reporting display only; payment endpoints must
always charge the immutable booking currency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock

import httpx
from sqlalchemy.orm import Session

from app.models.cms import Country

BASE_CURRENCY = "USD"
RATES_URL = "https://api.frankfurter.dev/v2/rates"
RATE_TTL = timedelta(hours=6)

# Offline continuity only. The API response replaces these values whenever it
# is available. AED is a fixed USD peg; the others are deliberately marked stale.
FALLBACK_USD_RATES: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "AED": Decimal("3.6725"),
    "AUD": Decimal("1.54"),
    "CAD": Decimal("1.37"),
    "CHF": Decimal("0.90"),
    "CNY": Decimal("7.25"),
    "EUR": Decimal("0.92"),
    "GBP": Decimal("0.78"),
    "HKD": Decimal("7.81"),
    "IDR": Decimal("16250"),
    "INR": Decimal("86"),
    "JPY": Decimal("158"),
    "KRW": Decimal("1380"),
    "MYR": Decimal("4.45"),
    "NZD": Decimal("1.68"),
    "QAR": Decimal("3.64"),
    "SAR": Decimal("3.75"),
    "SGD": Decimal("1.35"),
    "THB": Decimal("34.5"),
    "ZAR": Decimal("18.2"),
}

_cache_lock = Lock()
_cache: dict[str, object] = {}


def normalize_currency(code: str | None, fallback: str = BASE_CURRENCY) -> str:
    value = (code or fallback).strip().upper()
    return value if len(value) == 3 and value.isalpha() else fallback


def _live_usd_rates() -> tuple[dict[str, Decimal], str | None]:
    response = httpx.get(RATES_URL, params={"base": BASE_CURRENCY}, timeout=5.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Unexpected exchange-rate response")
    rates = {BASE_CURRENCY: Decimal("1")}
    rate_date = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        quote = normalize_currency(str(item.get("quote") or ""), "")
        rate = item.get("rate")
        if quote and rate is not None and Decimal(str(rate)) > 0:
            rates[quote] = Decimal(str(rate))
            rate_date = rate_date or item.get("date")
    if len(rates) < 2:
        raise ValueError("No exchange rates returned")
    return rates, str(rate_date) if rate_date else None


def get_usd_rates() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    with _cache_lock:
        expires_at = _cache.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at > now:
            return dict(_cache)
    try:
        live_rates, rate_date = _live_usd_rates()
        rates = {**FALLBACK_USD_RATES, **live_rates}
        source = "frankfurter"
        stale = False
    except (httpx.HTTPError, ValueError, TypeError, ArithmeticError):
        rates = dict(FALLBACK_USD_RATES)
        rate_date = None
        source = "fallback"
        stale = True
    payload: dict[str, object] = {
        "base": BASE_CURRENCY,
        "rates": rates,
        "source": source,
        "rate_date": rate_date,
        "is_stale": stale,
        "fetched_at": now.isoformat(),
        "expires_at": now + RATE_TTL,
    }
    with _cache_lock:
        _cache.clear()
        _cache.update(payload)
    return dict(payload)


def rates_for(base: str = BASE_CURRENCY) -> dict[str, object]:
    base = normalize_currency(base)
    payload = get_usd_rates()
    usd_rates = payload["rates"]
    assert isinstance(usd_rates, dict)
    if base not in usd_rates:
        base = BASE_CURRENCY
    divisor = Decimal(str(usd_rates[base]))
    converted = {code: float(Decimal(str(rate)) / divisor) for code, rate in usd_rates.items()}
    return {**payload, "base": base, "rates": converted, "expires_at": payload["expires_at"].isoformat()}


def convert_amount(amount: Decimal, from_currency: str, to_currency: str) -> tuple[Decimal, Decimal, dict[str, object]]:
    source = normalize_currency(from_currency)
    target = normalize_currency(to_currency)
    payload = get_usd_rates()
    rates = payload["rates"]
    assert isinstance(rates, dict)
    if source not in rates or target not in rates:
        raise ValueError(f"Unsupported currency conversion: {source} to {target}")
    rate = Decimal(str(rates[target])) / Decimal(str(rates[source]))
    converted = (Decimal(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return converted, rate, payload


def currency_for_country(db: Session, country_code: str | None) -> str | None:
    code = (country_code or "").strip().upper()
    if not code:
        return None
    row = db.query(Country).filter(Country.country_code == code, Country.status == "active").first()
    return normalize_currency(row.currency_code, "") if row and row.currency_code else None
