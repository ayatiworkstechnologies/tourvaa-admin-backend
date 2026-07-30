from datetime import datetime, timedelta
import hashlib
import secrets
from jose import jwt
from passlib.context import CryptContext
from app.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(received: str) -> str:
    """Bcrypt-hash a password. The frontend sends the plaintext password
    field directly over TLS (there is no client-side pre-hash step - an
    earlier design called for one, but it was never wired up on the
    frontend, and every seed script / test in this repo already relies on
    this function receiving plaintext), so this is simply bcrypt(plaintext)."""
    return password_context.hash(received)


def verify_password(received: str, stored_hash: str) -> bool:
    """Verify the value received from the frontend (plaintext, over TLS)
    against the stored bcrypt hash."""
    try:
        return password_context.verify(received, stored_hash)
    except Exception:
        return False


ROLE_SLUG_TO_PORTAL = {
    "supplier": "supplier",
    "agent-reseller": "agent",
    "customer": "customer",
    "affiliate": "affiliate",
    "super-admin": "admin",
    "admin": "admin",
}


def get_portal_for_role(role_slug: str) -> str:
    return ROLE_SLUG_TO_PORTAL.get((role_slug or "").lower(), "admin")


def create_token(data: dict, portal: str | None = None, *, token_type: str = "access", expires_minutes: int | None = None):
    token_data = data.copy()

    expire_time = datetime.utcnow() + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    if portal:
        token_data["portal"] = portal

    token_data.update({"exp": expire_time, "token_type": token_type})

    secret = settings.get_portal_secret(portal) if portal else settings.JWT_SECRET_KEY

    token = jwt.encode(
        token_data,
        secret,
        algorithm=settings.JWT_ALGORITHM
    )

    return token


def create_password_reset_token():
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return token, token_hash


def hash_reset_token(token: str):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_otp_code():
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    return code, code_hash


def hash_otp_code(code: str):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
