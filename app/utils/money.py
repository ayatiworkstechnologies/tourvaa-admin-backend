from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


MONEY_QUANT = Decimal("0.01")


def money(value: Any = 0) -> Decimal:
    if value is None:
        value = 0
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def money_str(value: Any = 0) -> str:
    return format(money(value), ".2f")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware_utc(value: datetime) -> datetime:
    """Treats a naive datetime as UTC instead of raising when compared
    against utcnow(). DateTime(timezone=True) columns are only actually
    timezone-aware on backends that support it (Postgres); SQLite has no
    native tz-aware datetime type, so SQLAlchemy silently reads such columns
    back as naive there, and `naive < aware` raises TypeError. Every value
    stored in these columns was written using utcnow() in the first place,
    so treating a naive read-back as UTC is correct, not a guess."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def json_safe(value: Any):
    if isinstance(value, Decimal):
        return money_str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value
