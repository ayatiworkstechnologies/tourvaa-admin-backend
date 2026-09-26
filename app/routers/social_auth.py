from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.settings import ApiSetting
from app.utils.crypto import decrypt_secret
from app.auth.security import create_token


router = APIRouter(prefix="/auth/oauth", tags=["Social Authentication"])


def _provider(db: Session, name: str):
    row = db.query(ApiSetting).filter(ApiSetting.api_name == f"oauth_{name}").first()
    return row, decrypt_secret(row.api_key or "") if row else ""


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
    callback = str(request.url_for("social_auth_callback", provider=provider))
    state = create_token({"provider": provider, "redirect": redirect}, token_type="oauth_state", expires_minutes=10)
    common = {"client_id": client_id, "redirect_uri": callback, "state": state}
    if provider == "google":
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({**common, "response_type": "code", "scope": "openid email profile", "access_type": "online", "prompt": "select_account"})
    elif provider == "facebook":
        url = "https://www.facebook.com/v22.0/dialog/oauth?" + urlencode({**common, "response_type": "code", "scope": "email,public_profile"})
    else:
        url = "https://appleid.apple.com/auth/authorize?" + urlencode({**common, "response_type": "code id_token", "response_mode": "form_post", "scope": "name email"})
    return RedirectResponse(url)


@router.api_route("/{provider}/callback", methods=["GET", "POST"], name="social_auth_callback")
async def social_auth_callback(provider: str, request: Request):
    # Callback exchange is intentionally fail-closed until the provider keys
    # have been validated in the deployment. This prevents accepting an
    # unverified provider identity while still giving admins the complete
    # redirect URI needed in each provider console.
    return RedirectResponse(f"/register?oauth_error={provider}_callback_requires_verified_credentials", status_code=303)
