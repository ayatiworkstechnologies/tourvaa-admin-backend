from datetime import datetime, timedelta
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.modules.common.email_templates import (
    render_database_email,
    password_changed_email,
    password_reset_email,
    pending_approval_email,
)
from app.modules.common.mailer import send_email, try_send_email
from app.modules.audit.models import AuditLog
from app.modules.audit.service import log_audit
from app.modules.users.models import User
from app.modules.users.models import UserRole
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.common.media import existing_storage_path
from app.security import (
    create_password_reset_token,
    create_token,
    hash_password,
    hash_reset_token,
    verify_password,
)

logger = logging.getLogger(__name__)
GENERIC_RESET_MESSAGE = "If an eligible account exists, a reset link has been sent."


def get_user_permissions(db: Session, role_ids: list[int]):
    permissions = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id.in_(role_ids))
        .filter(Permission.is_active == True)
        .distinct()
        .all()
    )

    return [
        {
            "id": permission.id,
            "name": permission.name,
            "slug": permission.slug,
            "module": permission.module,
            "action": permission.action,
        }
        for permission in permissions
    ]


def get_auth_user_payload(db: Session, user: User):
    role_ids = {user.role_id} if user.role_id else set()
    role_ids.update(user_role.role_id for user_role in user.user_roles)
    permissions = get_user_permissions(db, list(role_ids)) if role_ids else []
    roles = [
        {
            "id": user_role.role.id,
            "name": user_role.role.name,
            "slug": user_role.role.slug,
        }
        for user_role in user.user_roles
        if user_role.role
    ]

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "profile_image": existing_storage_path(user.profile_image),
        "role": {
            "id": user.role_id,
            "name": user.role.name if user.role else None,
            "slug": user.role.slug if user.role else None,
        },
        "roles": roles,
        "permissions": permissions,
    }


def build_password_reset_url(token: str, client_type: str | None = "web"):
    if client_type == "mobile":
        separator = "&" if "?" in settings.MOBILE_DEEP_LINK_URL else "?"
        return f"{settings.MOBILE_DEEP_LINK_URL}{separator}token={token}"

    return f"{settings.FRONTEND_URL}/reset-password?token={token}"


def register_user(db: Session, data):
    email = str(data.email).strip().lower()

    existing_user = db.query(User).filter(User.email == email).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    selected_role = None

    if data.role_id:
        selected_role = (
            db.query(Role)
            .filter(Role.id == data.role_id)
            .filter(Role.is_active == True)
            .first()
        )

        if not selected_role:
            raise HTTPException(status_code=400, detail="Selected role is not available")

        if selected_role.slug == "super-admin":
            user_count = db.query(User).count()

            if user_count > 0:
                raise HTTPException(
                    status_code=403,
                    detail="Super admin registration is restricted",
                )

    if not selected_role:
        selected_role = (
            db.query(Role)
            .filter(Role.slug == "customer")
            .filter(Role.is_active == True)
            .first()
        )

    is_customer = selected_role.slug == "customer" if selected_role else False

    new_user = User(
        name=data.name.strip(),
        email=email,
        phone=data.phone.strip(),
        profile_image=data.profile_image.strip(),
        address=data.address.strip(),
        country=data.country.strip(),
        state=data.state.strip(),
        city=data.city.strip(),
        pincode=data.pincode.strip(),
        password=hash_password(data.password),
        role_id=selected_role.id if selected_role else None,
        is_active=is_customer,
        approval_status="approved" if is_customer else "pending"
    )

    db.add(new_user)
    db.flush()
    if new_user.role_id:
        db.add(UserRole(user_id=new_user.id, role_id=new_user.role_id))
    db.commit()
    db.refresh(new_user)

    if not is_customer:
        subject, html = render_database_email(
            db,
            "registration_pending",
            {
                "name": new_user.name,
                "email": new_user.email,
                "phone": new_user.phone,
                "role_name": new_user.role.name if new_user.role else "Customer",
            },
            "Tourvaa registration received",
            pending_approval_email(new_user.name),
        )

        try_send_email(
            new_user.email,
            subject,
            html,
        )

    return new_user


def login_user(db: Session, data):
    email = str(data.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        log_audit(
            db,
            actor=None,
            action="login_failed",
            entity_type="auth",
            old_values=None,
            new_values={"email": email, "reason": "unknown_user"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(data.password, user.password):
        log_audit(
            db,
            actor=user,
            action="login_failed",
            entity_type="auth",
            entity_id=user.id,
            old_values=None,
            new_values={"email": email, "reason": "bad_password"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.approval_status == "pending":
        raise HTTPException(status_code=403, detail="Account is waiting for admin approval")

    if user.approval_status == "rejected":
        raise HTTPException(status_code=403, detail="Account approval was rejected")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    auth_user = get_auth_user_payload(db, user)

    token = create_token({
        "user_id": user.id,
        "email": user.email,
        "role": auth_user["role"]["slug"],
        "client_type": data.client_type or "web",
        "device_id": data.device_id,
        "token_version": user.token_version,
        "permissions": [
            permission["slug"] for permission in auth_user["permissions"]
        ],
    })

    log_audit(
        db,
        actor=user,
        action="login_success",
        entity_type="auth",
        entity_id=user.id,
        old_values=None,
        new_values={
            "client_type": data.client_type or "web",
            "device_id": data.device_id,
            "device_name": data.device_name,
        },
    )
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "client_type": data.client_type or "web",
        "user": auth_user,
    }


def refresh_user_token(db: Session, user: User, client_type: str | None = "web", device_id: str | None = None):
    auth_user = get_auth_user_payload(db, user)
    token = create_token({
        "user_id": user.id,
        "email": user.email,
        "role": auth_user["role"]["slug"],
        "client_type": client_type or "web",
        "device_id": device_id,
        "token_version": user.token_version,
        "permissions": [
            permission["slug"] for permission in auth_user["permissions"]
        ],
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "client_type": client_type or "web",
        "user": auth_user,
    }


def verify_email(db: Session, token: str | None = "", email: str | None = None):
    if email:
        user = db.query(User).filter(User.email == email.strip().lower()).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.approval_status == "approved" and user.is_active:
            return True

        user.approval_status = "approved"
        user.is_active = True
        db.commit()
        return True

    if token:
        validate_reset_token(db, token)
        return True

    raise HTTPException(status_code=400, detail="Verification token or email is required")


def get_login_history(db: Session, user: User, limit: int = 20):
    limit = max(1, min(limit, 100))
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "auth")
        .filter(AuditLog.action.in_(["login_success", "login_failed"]))
        .filter((AuditLog.actor_user_id == user.id) | (AuditLog.actor_user_id.is_(None)))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": row.id,
            "action": row.action,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "details": row.new_values or {},
            "created_at": row.created_at,
        }
        for row in rows
    ]


def force_logout_user(db: Session, target_user: User, actor: User | None = None, request=None):
    old_version = target_user.token_version
    target_user.token_version += 1
    log_audit(
        db,
        actor=actor,
        action="force_logout",
        entity_type="user",
        entity_id=target_user.id,
        old_values={"token_version": old_version},
        new_values={"token_version": target_user.token_version},
        request=request,
    )
    db.commit()
    db.refresh(target_user)
    return {"user_id": target_user.id, "token_version": target_user.token_version}


def forgot_password(db: Session, email: str, client_type: str | None = "web"):
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user:
        logger.info("Password reset requested for unknown email: %s", normalized_email)
        return False

    if user.approval_status == "pending":
        logger.info("Password reset skipped for pending user id=%s", user.id)
        return False

    if user.approval_status == "rejected":
        logger.info("Password reset skipped for rejected user id=%s", user.id)
        return False

    if not user.is_active:
        logger.info("Password reset skipped for inactive user id=%s", user.id)
        return False

    token, token_hash = create_password_reset_token()
    user.reset_password_token = token_hash
    user.reset_password_expires_at = datetime.utcnow() + timedelta(minutes=30)

    db.commit()

    reset_url = build_password_reset_url(token, client_type)
    subject, html = render_database_email(
        db,
        "password_reset",
        {
            "name": user.name,
            "email": user.email,
            "reset_url": reset_url,
            "button_text": "Reset Password",
            "button_url": reset_url,
        },
        "Reset your Tourvaa password",
        password_reset_email(user.name, reset_url),
    )

    try:
        send_email(
            user.email,
            subject,
            html,
        )
    except Exception as error:
        logger.warning("Password reset email failed for user id=%s: %s", user.id, error)

    return True


def reset_password(db: Session, token: str, password: str):
    token_hash = hash_reset_token(token)
    user = (
        db.query(User)
        .filter(User.reset_password_token == token_hash)
        .first()
    )

    if not user or not user.reset_password_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    expires_at = user.reset_password_expires_at

    if expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.approval_status != "approved" or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    user.password = hash_password(password)
    user.reset_password_token = None
    user.reset_password_expires_at = None
    user.token_version += 1

    db.commit()

    login_url = f"{settings.FRONTEND_URL}/login"
    subject, html = render_database_email(
        db,
        "password_changed",
        {
            "name": user.name,
            "email": user.email,
            "login_url": login_url,
            "button_text": "Login to Tourvaa",
            "button_url": login_url,
        },
        "Your Tourvaa password was changed",
        password_changed_email(user.name, login_url),
    )

    send_email(
        user.email,
        subject,
        html,
    )

    return True


def validate_reset_token(db: Session, token: str):
    if not token:
        raise HTTPException(status_code=400, detail="Reset token is missing")

    token_hash = hash_reset_token(token)
    user = db.query(User).filter(User.reset_password_token == token_hash).first()

    if not user or not user.reset_password_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.reset_password_expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.approval_status != "approved" or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    return True
