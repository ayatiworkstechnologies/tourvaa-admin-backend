from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.modules.common.auth import get_current_user, require_permission
from app.modules.common.ratelimit import check_rate_limit
from app.modules.users.models import User

from app.modules.auth.schemas import (
    ForceLogoutSchema,
    ForgotPasswordSchema,
    LoginSchema,
    RefreshTokenSchema,
    RegisterSchema,
    ResetPasswordSchema,
    VerifyEmailSchema,
)
from app.modules.auth.service import (
    force_logout_user,
    forgot_password,
    get_auth_user_payload,
    get_login_history,
    login_user,
    refresh_user_token,
    register_user,
    reset_password,
    validate_reset_token,
    verify_email,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
def register(data: RegisterSchema, db: Session = Depends(get_db)):
    user = register_user(db, data)

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
            "approval_status": user.approval_status
        }
    }


@router.post("/login")
def login(request: Request, data: LoginSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "login", max_calls=10, window_seconds=60)
    result = login_user(db, data)

    return {
        "status": "success",
        "message": "Login successful",
        "data": result
    }


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
    data: RefreshTokenSchema | None = None,
    db: Session = Depends(get_db),
):
    from jose import jwt as jose_jwt, JWTError
    from app.config import settings as _settings

    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization token missing")

    token = parts[1]
    try:
        # Decode without expiry check so an expired token can still be refreshed
        payload = jose_jwt.decode(
            token,
            _settings.JWT_SECRET_KEY,
            algorithms=[_settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    token_version = payload.get("token_version")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if token_version is None or token_version != user.token_version:
        raise HTTPException(status_code=401, detail="Session invalidated. Please log in again.")
    if user.approval_status != "approved" or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not active")

    refresh_data = data or RefreshTokenSchema()
    return {
        "status": "success",
        "message": "Token refreshed successfully",
        "data": refresh_user_token(
            db,
            user,
            client_type=refresh_data.client_type,
            device_id=refresh_data.device_id,
        ),
    }


@router.post("/verify-email")
def verify_email_request(request: Request, data: VerifyEmailSchema, db: Session = Depends(get_db)):
    check_rate_limit(request, "verify-email", max_calls=10, window_seconds=60)
    verify_email(db, data.token)
    return {
        "status": "success",
        "message": "Email verified successfully",
    }


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
