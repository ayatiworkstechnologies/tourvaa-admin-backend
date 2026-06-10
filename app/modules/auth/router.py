from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.modules.common.auth import get_current_user
from app.modules.users.models import User

from app.modules.auth.schemas import (
    ForgotPasswordSchema,
    LoginSchema,
    RegisterSchema,
    ResetPasswordSchema,
)
from app.modules.auth.service import (
    forgot_password,
    get_auth_user_payload,
    login_user,
    register_user,
    reset_password,
    validate_reset_token,
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
def login(data: LoginSchema, db: Session = Depends(get_db)):
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
def forgot_password_request(data: ForgotPasswordSchema, db: Session = Depends(get_db)):
    forgot_password(db, data.email, data.client_type)

    return {
        "status": "success",
        "message": "Reset link has been sent to your email"
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
