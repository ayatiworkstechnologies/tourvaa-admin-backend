from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwk, jwt
from sqlalchemy.orm import Session

from app.auth.security import create_token
from app.config import settings
from app.database import get_db
from app.models.settings import ApiSetting
from app.utils.crypto import decrypt_secret
from app.routers.auth import _set_auth_cookies
from app.routers.google_auth import _find_or_create_google_user
from app.services.auth import _finalize_login


router = APIRouter(prefix="/auth/oauth", tags=["Social Authentication"])


def _provider(db: Session, name: str):
    row = db.query(ApiSetting).filter(ApiSetting.api_name == f"oauth_{name}").first()
    return row, decrypt_secret(row.api_key or "") if row else ""


def _callback_url(provider: str) -> str:
    # OAuth runs through the frontend's same-origin /api rewrite in production.
    return f"{settings.FRONTEND_URL.rstrip('/')}/api/auth/oauth/{provider}/callback"


def _frontend_redirect(path: str = "/login", **params: str) -> RedirectResponse:
    target = f"{settings.FRONTEND_URL.rstrip('/')}{path}"
    if params:
        target = f"{target}?{urlencode(params)}"
    return RedirectResponse(target, status_code=303)


@router.get("/providers")
def provider_status(db: Session = Depends(get_db)):
    data = {}
    for name in ("google", "facebook", "apple"):
        row, client_id = _provider(db, name)
        data[name] = bool(row and row.is_enabled and client_id and row.api_secret)
    return {"status": "success", "data": data}


@router.get("/{provider}/start")
def start_social_auth(provider: str, request: Request, redirect: str = "", db: Session = Depends(get_db)):
    if provider not in {"google", "facebook", "apple"}:
        raise HTTPException(status_code=404, detail="Unknown social provider")
    row, client_id = _provider(db, provider)
    if not row or not row.is_enabled or not client_id or not row.api_secret:
        raise HTTPException(status_code=503, detail=f"{provider.title()} registration is not configured")
    callback = _callback_url(provider)
    state = create_token({"provider": provider, "redirect": redirect}, token_type="oauth_state", expires_minutes=10)
    common = {"client_id": client_id, "redirect_uri": callback, "state": state}
    if provider == "google":
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({**common, "response_type": "code", "scope": "openid email profile", "access_type": "online", "prompt": "select_account"})
    elif provider == "facebook":
        url = "https://www.facebook.com/v22.0/dialog/oauth?" + urlencode({**common, "response_type": "code", "scope": "email,public_profile"})
    else:
        url = "https://appleid.apple.com/auth/authorize?" + urlencode({**common, "response_type": "code id_token", "response_mode": "form_post", "scope": "name email"})
    return RedirectResponse(url)


async def _facebook_identity(row: ApiSetting, code: str, callback: str) -> dict:
    secret = decrypt_secret(row.api_secret or "")
    client_id = decrypt_secret(row.api_key or "")
    async with httpx.AsyncClient(timeout=15) as client:
        token = await client.get("https://graph.facebook.com/v22.0/oauth/access_token", params={
            "client_id": client_id, "client_secret": secret, "redirect_uri": callback, "code": code,
        })
        if token.status_code != 200 or not token.json().get("access_token"):
            raise HTTPException(status_code=401, detail="Facebook authorization code was rejected")
        profile = await client.get("https://graph.facebook.com/me", params={
            "fields": "id,name,email,picture.type(large)", "access_token": token.json()["access_token"],
        })
    if profile.status_code != 200:
        raise HTTPException(status_code=401, detail="Facebook identity verification failed")
    identity = profile.json()
    if not identity.get("email"):
        raise HTTPException(status_code=403, detail="Facebook must provide a verified email address")
    picture = ((identity.get("picture") or {}).get("data") or {}).get("url")
    return {"email": identity["email"], "name": identity.get("name"), "picture": picture, "email_verified": True}


def _apple_client_secret(row: ApiSetting, client_id: str) -> str:
    try:
        team_id, key_id = (row.api_url or "").strip().split(":", 1)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Apple Team ID and Key ID are not configured") from exc
    private_key = decrypt_secret(row.api_secret or "")
    if not team_id or not key_id or not private_key:
        raise HTTPException(status_code=503, detail="Apple OAuth is not configured")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"iss": team_id, "iat": now, "exp": now + timedelta(days=180), "aud": "https://appleid.apple.com", "sub": client_id},
        private_key, algorithm="ES256", headers={"kid": key_id},
    )


async def _apple_identity(row: ApiSetting, code: str, callback: str) -> dict:
    client_id = decrypt_secret(row.api_key or "")
    async with httpx.AsyncClient(timeout=15) as client:
        token = await client.post("https://appleid.apple.com/auth/token", data={
            "client_id": client_id, "client_secret": _apple_client_secret(row, client_id),
            "code": code, "grant_type": "authorization_code", "redirect_uri": callback,
        })
        if token.status_code != 200 or not token.json().get("id_token"):
            raise HTTPException(status_code=401, detail="Apple authorization code was rejected")
        id_token = token.json()["id_token"]
        header = jwt.get_unverified_header(id_token)
        keys = await client.get("https://appleid.apple.com/auth/keys")
    if keys.status_code != 200:
        raise HTTPException(status_code=401, detail="Apple signing keys are unavailable")
    key_data = next((item for item in keys.json().get("keys", []) if item.get("kid") == header.get("kid")), None)
    if not key_data:
        raise HTTPException(status_code=401, detail="Apple signing key was not found")
    public_key = jwk.construct(key_data, "RS256").to_pem().decode()
    try:
        identity = jwt.decode(id_token, public_key, algorithms=["RS256"], audience=client_id, issuer="https://appleid.apple.com")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Apple identity verification failed") from exc
    if not identity.get("email"):
        raise HTTPException(status_code=403, detail="Apple did not provide an email address")
    return {"email": identity["email"], "name": None, "picture": None, "email_verified": True}


@router.api_route(
    "/{provider}/callback",
    methods=["GET", "POST"],
    name="social_auth_callback",
    # One handler deliberately accepts both GET (Google/Facebook) and POST
    # (Apple). FastAPI otherwise emits the same generated operation ID twice
    # while building OpenAPI. These internal provider callbacks are not a
    # consumer API, so keep them out of the schema rather than publishing a
    # duplicate/ambiguous operation.
    include_in_schema=False,
)
async def social_auth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    if provider not in {"facebook", "apple"}:
        return _frontend_redirect(oauth_error="unknown_social_provider")
    form = await request.form() if request.method == "POST" else {}
    code = str(request.query_params.get("code") or form.get("code") or "")
    state = str(request.query_params.get("state") or form.get("state") or "")
    if not code or not state:
        return _frontend_redirect(oauth_error=f"{provider}_invalid_callback")
    try:
        state_payload = jwt.decode(state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if state_payload.get("token_type") != "oauth_state" or state_payload.get("provider") != provider:
            raise JWTError("Invalid OAuth state")
        row, client_id = _provider(db, provider)
        if not row or not row.is_enabled or not client_id or not row.api_secret:
            raise HTTPException(status_code=503, detail=f"{provider.title()} authentication is not configured")
        callback = _callback_url(provider)
        identity = await (_facebook_identity(row, code, callback) if provider == "facebook" else _apple_identity(row, code, callback))
        user = _find_or_create_google_user(db, identity)
        if user.two_factor_enabled:
            return _frontend_redirect(oauth_error=f"{provider}_2fa_requires_password_login")
        result = _finalize_login(db, user, SimpleNamespace(client_type="web-cookie", device_id=None, device_name=f"{provider.title()} OAuth"), request=request)
        requested = str(state_payload.get("redirect") or "")
        destination = requested if requested.startswith("/") and not requested.startswith("//") else result["user"].get("dashboard_route") or "/customer/dashboard"
        response = _frontend_redirect(destination)
        _set_auth_cookies(response, result, expose_access_token=False)
        return response
    except JWTError:
        return _frontend_redirect(oauth_error=f"{provider}_invalid_state")
    except (HTTPException, httpx.HTTPError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else f"{provider.title()} authentication failed"
        return _frontend_redirect(oauth_error=str(detail))
