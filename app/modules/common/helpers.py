import re
import unicodedata
from datetime import date, datetime
from typing import Any


def slugify(text: str) -> str:
    """Convert a string to a URL-safe slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text


def format_currency(amount: float, currency: str = "AED", decimals: int = 2) -> str:
    return f"{currency} {amount:,.{decimals}f}"


def parse_date(value: Any) -> date | None:
    """Parse a date from string (YYYY-MM-DD), date, or datetime. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def truncate(text: str, length: int = 100, suffix: str = "...") -> str:
    if len(text) <= length:
        return text
    return text[: length - len(suffix)].rstrip() + suffix


def mask_email(email: str) -> str:
    """Return e**@domain.com style masked email for logs/display."""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    visible = local[:1] if local else ""
    return f"{visible}{'*' * max(1, len(local) - 1)}@{domain}"


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dict into dot-separated keys."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
