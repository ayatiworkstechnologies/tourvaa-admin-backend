"""TOTP-based two-factor authentication: secret/QR provisioning, code
verification, and one-time backup codes (used when the authenticator device
isn't available)."""
import base64
import json
import secrets
from io import BytesIO

import pyotp

from app.auth.security import hash_password, verify_password

ISSUER = "Tourvaa"
BACKUP_CODE_COUNT = 8


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def verify_totp_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    try:
        # valid_window=1 tolerates the usual +/-30s clock drift between the
        # authenticator app and this server.
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False


def generate_qr_code_data_uri(provisioning_uri: str) -> str | None:
    """Returns a data: URI PNG for the QR code, or None if the qrcode/Pillow
    stack isn't available (callers should fall back to the raw secret for
    manual entry - the feature still works without a QR image)."""
    try:
        import qrcode

        img = qrcode.make(provisioning_uri)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    return [f"{secrets.token_hex(4)}" for _ in range(count)]


def hash_backup_codes(codes: list[str]) -> str:
    """Bcrypt-hash each code and return the JSON-serialized list for storage."""
    return json.dumps([hash_password(code) for code in codes])


def verify_and_consume_backup_code(stored_json: str | None, code: str) -> tuple[bool, str]:
    """Check `code` against the stored hashed backup codes. Returns
    (matched, updated_json) - the matched code is removed so it can't be
    reused, even when the caller doesn't persist the result (defensive)."""
    if not stored_json or not code:
        return False, stored_json or "[]"
    try:
        hashes: list[str] = json.loads(stored_json)
    except (ValueError, TypeError):
        return False, stored_json

    code = code.strip()
    for hashed in hashes:
        if verify_password(code, hashed):
            hashes.remove(hashed)
            return True, json.dumps(hashes)
    return False, stored_json
