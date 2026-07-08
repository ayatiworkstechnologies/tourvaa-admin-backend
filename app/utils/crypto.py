"""
Symmetric encryption for sensitive DB values (API keys, payment secrets).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
Key is derived from SETTINGS_ENCRYPTION_KEY env var, falling back to JWT_SECRET_KEY.

Encrypted values are stored with an "enc:" prefix so plain-text legacy values
can be read back safely without attempting decryption.
"""
import base64
import hashlib
import logging

logger = logging.getLogger(__name__)

_PREFIX = "enc:"
_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
        from app.config import settings

        raw_key = getattr(settings, "SETTINGS_ENCRYPTION_KEY", "") or settings.JWT_SECRET_KEY
        # Derive a 32-byte key deterministically from the raw key, then base64-url encode
        digest = hashlib.sha256(raw_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
        _fernet = Fernet(fernet_key)
    except Exception as exc:
        logger.error("crypto: could not initialize Fernet: %s", exc)
        _fernet = None
    return _fernet


def encrypt_secret(value: str | None) -> str | None:
    """Return an encrypted, prefixed string. Returns None/empty unchanged."""
    if not value:
        return value
    if value.startswith(_PREFIX):
        return value  # already encrypted
    f = _get_fernet()
    if not f:
        return value  # encryption unavailable — store plain (safe fallback)
    try:
        token = f.encrypt(value.encode()).decode()
        return f"{_PREFIX}{token}"
    except Exception as exc:
        logger.error("crypto: encryption failed: %s", exc)
        return value


def decrypt_secret(value: str | None) -> str | None:
    """Return the decrypted plaintext. Plain-text legacy values pass through unchanged."""
    if not value:
        return value
    if not value.startswith(_PREFIX):
        return value  # legacy plain-text — return as-is
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value[len(_PREFIX):].encode()).decode()
    except Exception as exc:
        logger.warning("crypto: decryption failed (returning empty): %s", exc)
        return ""
