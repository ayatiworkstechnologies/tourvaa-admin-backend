from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth.security import create_token
from app.config import settings
from app.database import get_db
from app.models.customers import Customer
from app.models.roles import Role
from app.models.users import User, UserRole, UserStatusHistory
from app.routers.auth import _set_auth_cookies
from app.services.auth import _finalize_login
from app.utils.money import utcnow


router = APIRouter(prefix="/auth", tags=["Google Authentication"])


def _frontend_redirect(path: str = "/login", **params: str) -> RedirectResponse:
    target = f"{settings.FRONTEND_URL.rstrip('/')}{path}"
    if params:
        target = f"{target}?{urlencode(params)}"
    return RedirectResponse(target, status_code=303)


@router.get("/google")
async def google_login(redirect: str = "") -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Google authentication is not configured")
    if redirect and (not redirect.startswith("/") or redirect.startswith("//")):
        raise HTTPException(status_code=400, detail="Invalid redirect path")

    state = create_token({"redirect": redirect}, token_type="google_oauth_state", expires_minutes=10)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


async def _google_identity(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Google authorization code was rejected")
        access_token = token_response.json().get("access_token", "")
        if not access_token:
            raise HTTPException(status_code=401, detail="Google did not return an access token")

        user_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Google identity verification failed")
        identity = user_response.json()

    email = str(identity.get("email", "")).strip().lower()
    if not email or identity.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="A verified Google email is required")
    return identity


def _find_or_create_google_user(db: Session, identity: dict) -> User:
    email = str(identity["email"]).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        if not user.email_verified:
            user.email_verified = True
            user.email_verified_at = user.email_verified_at or utcnow()
            db.commit()
            db.refresh(user)
        return user

    role = db.query(Role).filter(Role.slug == "customer", Role.is_active == True).first()
    if not role:
        raise HTTPException(status_code=503, detail="Customer registration is unavailable")

    name = str(identity.get("name") or email.split("@", 1)[0]).strip()[:150]
    picture = str(identity.get("picture") or "").strip()[:255]
    user = User(
        name=name, email=email, profile_image=picture, password=None,
        role_id=role.id, user_type="CUSTOMER", is_active=True,
        approval_status="not_required", email_verified=True,
        email_verified_at=utcnow(), account_status="ACTIVE",
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(UserStatusHistory(user_id=user.id, to_status="ACTIVE", reason="Registered with Google"))
    name_parts = name.split(" ", 1)
    db.add(Customer(
        user_id=user.id, first_name=name_parts[0],
        last_name=name_parts[1] if len(name_parts) > 1 else "",
        full_name=name, email=email, profile_image=picture,
        status="active", email_verified=True,
    ))
    db.commit()
    db.refresh(user)
    return user


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        return _frontend_redirect(oauth_error=f"google_{error}")
    if not code or not state:
        return _frontend_redirect(oauth_error="google_invalid_callback")

    try:
        state_payload = jwt.decode(state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if state_payload.get("token_type") != "google_oauth_state":
            raise JWTError("Invalid OAuth state")
        identity = await _google_identity(code)
        user = _find_or_create_google_user(db, identity)
        if user.two_factor_enabled:
            return _frontend_redirect(oauth_error="google_2fa_requires_password_login")

        result = _finalize_login(
            db, user,
            SimpleNamespace(client_type="web-cookie", device_id=None, device_name="Google OAuth"),
            request=request,
        )
        requested_redirect = str(state_payload.get("redirect") or "")
        dashboard = result["user"].get("dashboard_route") or "/customer/dashboard"
        destination = requested_redirect if requested_redirect.startswith("/") and not requested_redirect.startswith("//") else dashboard
        response = _frontend_redirect(destination)
        _set_auth_cookies(response, result, expose_access_token=False)
        return response
    except JWTError:
        return _frontend_redirect(oauth_error="google_invalid_state")
    except (HTTPException, httpx.HTTPError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Google authentication failed"
        return _frontend_redirect(oauth_error=str(detail))
