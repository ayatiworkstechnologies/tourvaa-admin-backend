from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.permissions import get_current_user, get_token_user_including_inactive, require_permission
from app.utils.ratelimit import check_rate_limit
from app.models.users import User
from app.models.roles import Role
from app.config import settings
from app.auth.security import create_token

from app.schemas.auth import (
    ForceLogoutSchema,
    CompleteRegistrationSchema,
    ChangeRegistrationEmailSchema,
    ForgotPasswordSchema,
    LoginSchema,
    RefreshTokenSchema,
    RegisterSchema,
    ResendVerificationSchema,
    ResetPasswordSchema,
    VerifyEmailSchema,
    UnifiedRegisterSchema,
)
from app.services.auth import (
    force_logout_user,
    forgot_password,
    get_auth_user_payload,
    get_login_history,
    login_user,
    change_registration_email,
    complete_registration,
    refresh_user_token,
    register_user,
    register_unified_user,
    resend_registration_verification,
    reset_password,
    validate_reset_token,
    validate_registration_token,
    verify_email,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
ACCESS_COOKIE_NAME = "tourvaa_access"
REFRESH_COOKIE_NAME = "tourvaa_refresh"


def _set_auth_cookies(response: Response, result: dict, *, expose_access_token: bool = True) -> dict:
    access_token = result.get("access_token", "")
    refresh_token = result.pop("_refresh_token", "")
    secure = settings.APP_ENV.lower() == "production"
    response.set_cookie(ACCESS_COOKIE_NAME, access_token, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(REFRESH_COOKIE_NAME, refresh_token, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, httponly=True, secure=secure, samesite="lax", path="/api/auth")
    if not expose_access_token:
        result.pop("access_token", None)
        result.pop("token_type", None)
    return result


def _clear_auth_cookies(response: Response) -> None:
    secure = settings.APP_ENV.lower() == "production"
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth", httponly=True, secure=secure, samesite="lax")


def _register_with_role(role_slug: str, data: RegisterSchema, db: Session):
    role = (
        db.query(Role)
        .filter(Role.slug == role_slug)
        .filter(Role.is_active == True)
        .first()
    )
    if not role:
        raise HTTPException(status_code=400, detail="Registration role is not available")
    return register_user(db, data.model_copy(update={"role_id": role.id}))


def _registration_response(user: User):
    change_token = create_token(
        {"user_id": user.id, "token_version": user.token_version},
        token_type="registration_change",
        expires_minutes=30,
    )
    return {
        "status": "success",
        "message": "User registered successfully",
        "data": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": {
                "id": user.role.id if user.role else None,
                "name": user.role.name if user.role else None,
                "slug": user.role.slug if user.role else None,
            },
            "approval_status": user.approval_status,
            "account_status": user.account_status,
            "registration_change_token": change_token,
        },
    }

@router.post("/register")
def register(data: UnifiedRegisterSchema, db: Session = Depends(get_db)):
    user = register_unified_user(db, data)

    return _registration_response(user)


@router.post("/register/customer")
def register_customer(data: RegisterSchema, db: Session = Depends(get_db)):
    return _registration_response(_register_with_role("customer", data, db))


@router.post("/register/supplier")
def register_supplier(data: RegisterSchema, db: Session = Depends(get_db)):
    return _registration_response(_register_with_role("supplier", data, db))


@router.post("/register/agent")
def register_agent(data: RegisterSchema, db: Session = Depends(get_db)):
    return _registration_response(_register_with_role("agent-reseller", data, db))


@router.post("/login")
def login(request: Request, response: Response, data: LoginSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "login", max_calls=10, window_seconds=60)
    result = _set_auth_cookies(response, login_user(db, data, request=request), expose_access_token=data.client_type != "web-cookie")

    return {
        "status": "success",
        "message": "Account status returned" if result.get("account_restricted") else "Login successful",
        "data": result
    }


@router.get("/account-status")
def account_status(
    current_user: User = Depends(get_token_user_including_inactive),
    db: Session = Depends(get_db),
):
    return {"status": "success", "data": {"user": get_auth_user_payload(db, current_user)}}


@router.get("/me")
def current_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "status": "success",
        "message": "Session loaded",
        "data": {
            "user": get_auth_user_payload(db, current_user),
        },
    }


@router.post("/forgot-password")
def forgot_password_request(request: Request, data: ForgotPasswordSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "forgot-password", max_calls=5, window_seconds=300)
    forgot_password(db, data.email, data.client_type)

    return {
        "status": "success",
        "message": "A password reset link has been sent to your email address."
    }


@router.post("/reset-password")
def reset_password_request(data: ResetPasswordSchema, db: Session = Depends(get_db)):
    reset_password(db, data.token, data.password)

    return {
        "status": "success",
        "message": "Password reset successfully"
    }


@router.get("/reset-password/validate")
def validate_reset_password_link(
    token: str = Query(default=""),
    db: Session = Depends(get_db),
):
    validate_reset_token(db, token)

    return {
        "status": "success",
        "message": "Reset link is valid"
    }


@router.post("/refresh-token")
def refresh_token(
    request: Request,
    response: Response,
    data: RefreshTokenSchema | None = None,
    db: Session = Depends(get_db),
):
    from jose import jwt as jose_jwt, JWTError
    from app.config import settings as _settings

    token = request.cookies.get(REFRESH_COOKIE_NAME, "")
    if not token:
        authorization = request.headers.get("Authorization", "")
        parts = authorization.split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else ""
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token missing")
    try:
        # Read portal claim without full verification to pick the correct secret
        try:
            unverified = jose_jwt.get_unverified_claims(token)
            portal = unverified.get("portal")
        except JWTError:
            portal = None
        secret = _settings.get_portal_secret(portal) if portal else _settings.JWT_SECRET_KEY

        # Decode without expiry check so an expired token can still be refreshed
        payload = jose_jwt.decode(
            token,
            secret,
            algorithms=[_settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if request.cookies.get(REFRESH_COOKIE_NAME) and payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("user_id")
    token_version = payload.get("token_version")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if token_version is None or token_version != user.token_version:
        raise HTTPException(status_code=401, detail="Session invalidated. Please log in again.")
    if user.account_status != "ACTIVE" or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not active")

    refresh_data = data or RefreshTokenSchema()
    result = _set_auth_cookies(response, refresh_user_token(
        db,
        user,
        client_type=refresh_data.client_type,
        device_id=refresh_data.device_id,
    ), expose_access_token=refresh_data.client_type != "web-cookie")
    return {
        "status": "success",
        "message": "Token refreshed successfully",
        "data": result,
    }

@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    data: RefreshTokenSchema | None = None,
    db: Session = Depends(get_db),
):
    return refresh_token(request, response, data, db)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_token_user_including_inactive),
    db: Session = Depends(get_db),
):
    force_logout_user(db, current_user, actor=current_user, request=request)
    _clear_auth_cookies(response)
    return {
        "status": "success",
        "message": "Logged out successfully",
    }

@router.post("/verify-email")
def verify_email_request(request: Request, data: VerifyEmailSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "verify-email", max_calls=10, window_seconds=60)
    verify_email(db, data.token)
    return {
        "status": "success",
        "message": "Email verified successfully",
    }


@router.get("/verify-email/validate")
def validate_verification_link(token: str = Query(default=""), db: Session = Depends(get_db)):
    return {"status": "success", "data": validate_registration_token(db, token)}


@router.post("/complete-registration")
def complete_registration_request(data: CompleteRegistrationSchema, db: Session = Depends(get_db)):
    user = complete_registration(db, data.token, data.password)
    return {
        "status": "success",
        "message": "Password created. Your account is pending administrator verification.",
        "data": {"account_status": user.account_status},
    }


@router.post("/resend-verification")
def resend_verification(request: Request, data: ResendVerificationSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "resend-verification", max_calls=3, window_seconds=300)
    resend_registration_verification(db, str(data.email), data.redirect)
    return {"status": "success", "message": "If the account is pending, a new verification email has been sent."}


@router.post("/change-registration-email")
def change_email(request: Request, data: ChangeRegistrationEmailSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "change-registration-email", max_calls=3, window_seconds=300)
    user = change_registration_email(db, data.change_token, str(data.email), data.redirect)
    return {"status": "success", "message": "Email updated and verification link sent.", "data": {"email": user.email}}


@router.get("/login-history")
def login_history(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "status": "success",
        "data": get_login_history(db, current_user, limit=limit),
    }


@router.post("/force-logout")
def force_logout(
    request: Request,
    data: ForceLogoutSchema | None = None,
    current_user: User = Depends(require_permission("update-users")),
    db: Session = Depends(get_db),
):
    target_user = current_user
    if data and data.user_id:
        target_user = db.query(User).filter(User.id == data.user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

    return {
        "status": "success",
        "message": "User sessions invalidated successfully",
        "data": force_logout_user(db, target_user, actor=current_user, request=request),
    }


