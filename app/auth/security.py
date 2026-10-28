from datetime import timedelta
import hashlib
import secrets
from jose import ExpiredSignatureError, JWTError, jwt
from fastapi import HTTPException
from passlib.context import CryptContext
from app.config import settings
from app.utils.money import utcnow

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Signing keys are loaded at process startup. Rotating either domain key
# intentionally invalidates that domain's existing sessions.


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
    "sub-admin": "admin",
}


def get_portal_for_role(role_slug: str) -> str:
    # Every role created from Admin -> Roles is a back-office role unless it
    # is one of the explicit customer/supplier/agent/affiliate portal roles
    # above. It uses the Admin shell, while its own assigned permissions
    # remain the sole authority for menus and API actions.
    return ROLE_SLUG_TO_PORTAL.get((role_slug or "").lower(), "admin")


def get_auth_domain_for_portal(portal: str | None) -> str:
    return "admin" if portal == "admin" else "normal"


def get_auth_domain_for_role(role_slug: str) -> str:
    return get_auth_domain_for_portal(get_portal_for_role(role_slug))


def decode_auth_token(token: str) -> dict:
    """Verify a token against exactly one of the two authentication domains."""
    expired = False
    for auth_domain in ("admin", "normal"):
        try:
            payload = jwt.decode(
                token,
                settings.get_auth_secret(auth_domain),
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("auth_domain") != auth_domain:
                raise HTTPException(status_code=401, detail="Invalid token domain")
            return payload
        except ExpiredSignatureError:
            expired = True
        except JWTError:
            continue
    if expired:
        raise HTTPException(status_code=401, detail="Token has expired")
    raise HTTPException(status_code=401, detail="Invalid token")


def create_token(data: dict, portal: str | None = None, *, token_type: str = "access", expires_minutes: int | None = None):
    token_data = data.copy()

    expire_time = utcnow() + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    resolved_portal = portal or token_data.get("portal") or "customer"
    auth_domain = get_auth_domain_for_portal(resolved_portal)
    token_data["portal"] = resolved_portal
    token_data["auth_domain"] = auth_domain

    token_data.update({"exp": expire_time, "token_type": token_type})

    secret = settings.get_auth_secret(auth_domain)

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
