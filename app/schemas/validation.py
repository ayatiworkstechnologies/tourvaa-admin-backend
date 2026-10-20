"""Shared, transport-level validation for contact details."""

import re


E164_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,19}$")
SIMPLE_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_e164_phone(value: str | None, *, required: bool = False) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        if required:
            raise ValueError("Enter a valid mobile number")
        return None
    if not E164_PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid mobile number in international format, for example +919876543210")
    return normalized


def normalize_optional_email(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    if not SIMPLE_EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address")
    return normalized
