from datetime import timedelta
import logging
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.utils.money import utcnow
from app.utils.email_templates import (
    render_database_email,
    password_changed_email,
    password_reset_email,
    email_verification_email,
    otp_login_email,
    registration_password_created_email,
)
from app.utils.mailer import send_email, try_send_email
from app.models.audit import AuditLog
from app.services.audit import log_audit
from app.models.users import User, UserRole, UserStatusHistory
from app.models.roles import Role
from app.models.permissions import Permission, RolePermission
from app.models.customers import Customer
from app.models.suppliers import Supplier
from app.models.agents import Agent
from app.models.affiliates import Affiliate
from app.models.sessions import LoginHistory
from app.services.sessions import create_session
from app.utils.media import existing_storage_path
from app.auth.security import (
    create_otp_code,
    create_password_reset_token,
    create_token,
    get_portal_for_role,
    hash_otp_code,
    hash_password,
    hash_reset_token,
    verify_password,
)

logger = logging.getLogger(__name__)


def _request_ip(request) -> str | None:
    return request.client.host if request and request.client else None


def _request_user_agent(request) -> str | None:
    return request.headers.get("user-agent") if request else None


def _record_login_history(db: Session, *, data, email: str, status: str, user: User | None = None, failure_reason: str | None = None, session_id: str | None = None, request=None) -> None:
    db.add(
        LoginHistory(
            user_id=user.id if user else None,
            email=email,
            status=status,
            failure_reason=failure_reason,
            client_type=data.client_type or "web",
            device_id=data.device_id,
            device_name=data.device_name,
            ip_address=_request_ip(request),
            user_agent=_request_user_agent(request),
            session_id=session_id,
        )
    )


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

    customer_id = None
    supplier_id = None
    supplier_approval_status = "NOT_REQUIRED"
    agent_id = None
    affiliate_id = None
    role_slug = user.role.slug if user.role else ""
    if "customer" in role_slug:
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        if customer:
            customer_id = customer.id
    elif "supplier" in role_slug.lower():
        from app.models.suppliers import Supplier
        supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
        if supplier:
            supplier_id = supplier.id
            supplier_approval_status = (supplier.approval_status or "PENDING").upper()
    elif "agent" in role_slug.lower():
        from app.models.agents import Agent
        agent = db.query(Agent).filter(Agent.user_id == user.id).first()
        if agent:
            agent_id = agent.id
    elif "affiliate" in role_slug.lower():
        affiliate = db.query(Affiliate).filter(Affiliate.user_id == user.id).first()
        if affiliate:
            affiliate_id = affiliate.id

    return {
        "id": user.id,
        "name": user.name,
        "first_name": (user.name or "").split(" ", 1)[0],
        "email": user.email,
        "phone": user.phone,
        "country_code": user.country_code,
        "mobile_number": user.mobile_number,
        "user_type": user.user_type,
        "email_verified": user.email_verified,
        "admin_verified": user.admin_verified,
        "account_status": user.account_status,
        "profile_image": existing_storage_path(user.profile_image),
        "role": {
            "id": user.role_id,
            "name": user.role.name if user.role else None,
            "slug": user.role.slug if user.role else None,
        },
        "roles": roles,
        "permissions": permissions,
        "customer_id": customer_id,
        "supplier_id": supplier_id,
        "supplier_approval_status": supplier_approval_status,
        "agent_id": agent_id,
        "affiliate_id": affiliate_id,
        "dashboard_route": {
            "customer": "/customer/dashboard",
            "agent-reseller": "/agent/dashboard",
            "supplier": "/supplier/dashboard",
            "affiliate": "/affiliate/dashboard",
        }.get(role_slug, "/admin/dashboard"),
    }


def build_password_reset_url(token: str, client_type: str | None = "web"):
    if client_type == "mobile":
        separator = "&" if "?" in settings.MOBILE_DEEP_LINK_URL else "?"
        return f"{settings.MOBILE_DEEP_LINK_URL}{separator}token={token}"

    return f"{settings.FRONTEND_URL}/reset-password?token={token}"

def build_email_verification_url(token: str, redirect: str | None = None):
    url = f"{settings.FRONTEND_URL}/auth/verify-email?token={token}"
    return f"{url}&redirect={quote(redirect, safe='')}" if redirect else url


def build_portal_login_url(user: User):
    role_slug = user.role.slug if user.role else ""
    role_param = {
        "customer": "traveller",
        "agent-reseller": "agent",
        "supplier": "supplier",
        "affiliate": "affiliate",
    }.get(role_slug)
    if role_param:
        return f"{settings.FRONTEND_URL}/login?role={role_param}"
    return f"{settings.FRONTEND_URL}/login"


def portal_display_name(user: User):
    role_slug = user.role.slug if user.role else ""
    return {
        "customer": "traveller",
        "agent-reseller": "agent",
        "supplier": "supplier",
        "affiliate": "affiliate",
    }.get(role_slug, "admin")


def send_email_verification(db: Session, user: User, token: str, redirect: str | None = None):
    verification_url = build_email_verification_url(token, redirect)
    subject, html = render_database_email(
        db,
        "email_verification",
        {
            "name": user.name,
            "email": user.email,
            "verification_url": verification_url,
            "button_text": "Verify Email & Create Password",
            "button_url": verification_url,
        },
        "Verify your Tourvaa email and create your password",
        email_verification_email(user.name, verification_url),
    )
    try_send_email(user.email, subject, html, template_key="email_verification")


def register_unified_user(db: Session, data):
    email = str(data.email).strip().lower()
    phone = f"{data.country_code}{data.mobile_number}"
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    if db.query(User).filter(or_(User.mobile_number == phone, User.phone == phone)).first():
        raise HTTPException(status_code=400, detail="Mobile number already exists")

    role_slug = {"CUSTOMER": "customer", "AGENT": "agent-reseller", "SUPPLIER": "supplier", "AFFILIATE": "affiliate"}[data.account_type]
    role = db.query(Role).filter(Role.slug == role_slug, Role.is_active == True).first()
    if not role:
        raise HTTPException(status_code=400, detail="Selected account type is not available")

    now = utcnow()
    token, token_hash = create_password_reset_token()

    user = User(
        name=data.first_name,
        email=email,
        phone=phone,
        country_code=data.country_code,
        mobile_number=phone,
        password=None,
        role_id=role.id,
        user_type=data.account_type,
        is_active=False,
        approval_status="PENDING" if data.account_type in {"SUPPLIER", "AFFILIATE"} else "NOT_REQUIRED",
        email_verified=False,
        admin_verified=False,
        password_created_at=None,
        account_status="PENDING_EMAIL_VERIFICATION",
        email_verification_token=token_hash,
        email_verification_expires_at=now + timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES),
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(UserStatusHistory(
        user_id=user.id,
        to_status=user.account_status,
        reason=f"{data.account_type.title()} email verification started",
    ))

    if role_slug == "customer":
        db.add(Customer(user_id=user.id, first_name=user.name, last_name="", full_name=user.name, email=email, phone=phone, status="inactive", email_verified=False))
    elif role_slug == "supplier":
        db.add(Supplier(user_id=user.id, supplier_name=user.name, status="inactive", approval_status="PENDING"))
    elif role_slug == "affiliate":
        db.add(Affiliate(user_id=user.id, name=user.name, email=email, phone=phone, status="inactive", approval_status="pending"))
    else:
        db.add(Agent(user_id=user.id, agent_name=user.name, status="inactive", approval_status="pending"))

    log_audit(
        db,
        actor=user,
        action="registration",
        entity_type="auth",
        entity_id=user.id,
        new_values={"email": user.email, "user_type": user.user_type, "account_status": user.account_status},
    )
    db.commit()
    db.refresh(user)
    send_email_verification(db, user, token, data.redirect)
    log_audit(
        db,
        actor=user,
        action="verification_email_sent",
        entity_type="auth",
        entity_id=user.id,
        new_values={"email": user.email},
    )
    db.commit()
    return user


def validate_registration_token(db: Session, token: str):
    user = _registration_token_user(db, token)
    if user.account_status == "PENDING_EMAIL_VERIFICATION":
        old_status = user.account_status
        user.account_status = "PENDING_PASSWORD_CREATION"
        db.add(UserStatusHistory(user_id=user.id, from_status=old_status, to_status=user.account_status, reason="Email link opened"))
        db.commit()
    return {"email": user.email, "account_type": user.user_type}


def _registration_token_user(db: Session, token: str):
    if not token:
        raise HTTPException(status_code=400, detail="Verification token is required")
    user = db.query(User).filter(User.email_verification_token == hash_reset_token(token)).first()
    if not user or not user.email_verification_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    # MySQL strips tzinfo on round-trip even though the column is declared
    # DateTime(timezone=True), so a freshly-queried value here is naive while
    # utcnow() is tz-aware - compare on equal footing rather than crashing.
    now = utcnow()
    expires_at = user.email_verification_expires_at
    if expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    if expires_at < now:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if user.account_status not in {"PENDING_EMAIL_VERIFICATION", "PENDING_PASSWORD_CREATION"}:
        raise HTTPException(status_code=400, detail="Verification link has already been used")
    return user


def complete_registration(db: Session, token: str, password: str):
    user = _registration_token_user(db, token)
    old_status = user.account_status
    now = utcnow()
    user.password = hash_password(password)
    user.password_created_at = now
    user.email_verified = True
    user.email_verified_at = now
    user.email_verification_token = None
    user.email_verification_expires_at = None
    user.account_status = "ACTIVE"
    user.is_active = True
    user.approval_status = "PENDING" if user.user_type in {"SUPPLIER", "AFFILIATE"} else "NOT_REQUIRED"

    customer = db.query(Customer).filter(Customer.user_id == user.id).first()
    if customer:
        customer.email_verified = True
        customer.status = "active"

    agent = db.query(Agent).filter(Agent.user_id == user.id).first()
    if agent:
        agent.status = "active"
        agent.approval_status = "pending"
        agent.approved_at = None
        agent.rejection_reason = None

    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if supplier:
        supplier.status = "active"
        supplier.approval_status = "PENDING"
        supplier.approved_at = None
        supplier.rejection_reason = None

    affiliate = db.query(Affiliate).filter(Affiliate.user_id == user.id).first()
    if affiliate:
        affiliate.status = "active"
        affiliate.approval_status = "pending"
        affiliate.approved_at = None
        affiliate.rejection_reason = None

    db.add(UserStatusHistory(
        user_id=user.id,
        from_status=old_status,
        to_status=user.account_status,
        reason="Email verified and password created; account activated",
    ))
    log_audit(
        db,
        actor=user,
        action="email_verified",
        entity_type="auth",
        entity_id=user.id,
        new_values={"email_verified": True},
    )
    log_audit(
        db,
        actor=user,
        action="password_created",
        entity_type="auth",
        entity_id=user.id,
        new_values={"account_status": "ACTIVE"},
    )
    if supplier:
        from app.utils.notification_triggers import notify_supplier_approval_pending
        notify_supplier_approval_pending(
            db,
            supplier_id=supplier.id,
            supplier_name=supplier.supplier_name,
            user_id=user.id,
        )
    if affiliate:
        from app.services.notifications import notify_admins
        notify_admins(db, notification_type="affiliate_application", title="New Affiliate Application", message=f"{affiliate.name} applied to become an affiliate.", entity_type="affiliate", entity_id=affiliate.id)
    db.commit()
    try:
        login_url = build_portal_login_url(user)
        subject, html = render_database_email(
            db,
            "registration_password_created",
            {
                "name": user.name,
                "email": user.email,
                "portal_name": portal_display_name(user),
                "login_url": login_url,
                "button_text": "Login to Tourvaa",
                "button_url": login_url,
            },
            "Your Tourvaa account is ready to sign in",
            registration_password_created_email(user.name, login_url),
        )
        try_send_email(user.email, subject, html, template_key="registration_password_created")
    except Exception as exc:
        logger.warning("Password-created login email failed for user id=%s: %s", user.id, exc)
    return user


def resend_registration_verification(db: Session, email: str, redirect: str | None = None):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user:
        return True
    if user.account_status not in {"PENDING_EMAIL_VERIFICATION", "PENDING_PASSWORD_CREATION"}:
        raise HTTPException(status_code=400, detail="This account no longer needs email verification")
    token, token_hash = create_password_reset_token()
    user.account_status = "PENDING_EMAIL_VERIFICATION"
    user.email_verification_token = token_hash
    user.email_verification_expires_at = utcnow() + timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
    db.commit()
    send_email_verification(db, user, token, redirect)
    return True


def change_registration_email(db: Session, change_token: str, email: str, redirect: str | None = None):
    from jose import JWTError, jwt
    try:
        payload = jwt.decode(change_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Change-email session has expired")
    if payload.get("token_type") != "registration_change":
        raise HTTPException(status_code=400, detail="Invalid change-email session")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or payload.get("token_version") != user.token_version:
        raise HTTPException(status_code=400, detail="Invalid change-email session")
    if user.account_status not in {"PENDING_EMAIL_VERIFICATION", "PENDING_PASSWORD_CREATION"}:
        raise HTTPException(status_code=400, detail="Email can no longer be changed")
    normalized = email.strip().lower()
    if db.query(User).filter(User.email == normalized, User.id != user.id).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user.email = normalized
    customer = db.query(Customer).filter(Customer.user_id == user.id).first()
    if customer:
        customer.email = normalized
    token, token_hash = create_password_reset_token()
    user.account_status = "PENDING_EMAIL_VERIFICATION"
    user.email_verification_token = token_hash
    user.email_verification_expires_at = utcnow() + timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
    db.commit()
    send_email_verification(db, user, token, redirect)
    return user

def login_user(db: Session, data, request=None):
    identifier = data.login_identifier
    digits = "".join(character for character in identifier if character.isdigit())
    normalized_phone = f"+{digits}" if digits else ""
    user = db.query(User).filter(or_(
        User.email == identifier,
        User.phone == identifier,
        User.mobile_number == normalized_phone,
    )).first()
    email = user.email if user else identifier

    if not user:
        _record_login_history(db, data=data, email=email, status="failed", failure_reason="unknown_user", request=request)
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

    if user.locked_until and user.locked_until > utcnow():
        _record_login_history(db, data=data, email=email, status="failed", user=user, failure_reason="account_locked", request=request)
        db.commit()
        raise HTTPException(
            status_code=423,
            detail="Too many failed attempts. Your account is temporarily locked - please try again later or reset your password.",
        )

    if not user.password or not verify_password(data.password, user.password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            user.locked_until = utcnow() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        _record_login_history(db, data=data, email=email, status="failed", user=user, failure_reason="bad_password", request=request)
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

    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

    if settings.REQUIRE_EMAIL_VERIFICATION and user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER", "AFFILIATE"} and not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Email verification is required before login")

    if user.two_factor_enabled:
        _record_login_history(db, data=data, email=email, status="2fa_pending", user=user, request=request)
        db.commit()
        return {
            "two_factor_required": True,
            "pending_token": create_token(
                {"user_id": user.id}, token_type="2fa_pending", expires_minutes=5,
            ),
        }

    return _finalize_login(db, user, data, request=request)


def _finalize_login(db: Session, user: User, data, request=None):
    """Shared tail of login_user()/verify_otp_and_login(): issue tokens, start a
    session, and record history/audit. `data` only needs .client_type/.device_id/
    .device_name (LoginSchema and OtpVerifySchema both satisfy this)."""
    email = user.email
    auth_user = get_auth_user_payload(db, user)
    role_slug = auth_user["role"]["slug"]
    portal = get_portal_for_role(role_slug)

    if user.account_status != "ACTIVE" or not user.is_active:
        token = create_token({
            "user_id": user.id,
            "email": user.email,
            "role": role_slug,
            "portal": portal,
            "client_type": data.client_type or "web",
            "device_id": data.device_id,
            "token_version": user.token_version,
        }, portal=portal)
        _record_login_history(db, data=data, email=email, status="restricted", user=user, failure_reason=user.account_status, request=request)
        db.commit()
        if user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER", "AFFILIATE"}:
            raise HTTPException(
                status_code=403,
                detail=f"Account is {user.account_status.lower().replace('_', ' ')}",
            )
        return {
            "access_token": token,
            "_refresh_token": "",
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "account_restricted": True,
            "account_status": user.account_status,
            "user": auth_user,
        }

    # Session is created before the tokens so its session_id can be embedded
    # as a token claim - that's what lets a single "revoke this session"
    # action (see services/sessions.revoke_session) actually invalidate the
    # token, instead of only marking a UserSession row for display purposes.
    try:
        session = create_session(db, user, request=request)
    except Exception as error:
        logger.warning("Login session tracking failed for user %s: %s", user.id, error)
        session = None

    token_claims = {
        "user_id": user.id,
        "email": user.email,
        "role": role_slug,
        "portal": portal,
        "client_type": data.client_type or "web",
        "device_id": data.device_id,
        "token_version": user.token_version,
        "session_id": session.session_id if session else None,
    }
    token = create_token(token_claims, portal=portal)
    refresh_token = create_token(
        token_claims,
        portal=portal,
        token_type="refresh",
        expires_minutes=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60,
    )

    if session:
        _record_login_history(
            db,
            data=data,
            email=email,
            status="success",
            user=user,
            session_id=session.session_id,
            request=request,
        )

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
    user.last_login_at = utcnow()
    db.commit()

    return {
        "access_token": token,
        "_refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "client_type": data.client_type or "web",
        "session_id": session.session_id if session else None,
        "user": auth_user,
    }


def setup_two_factor(db: Session, user: User) -> dict:
    """Generate a new TOTP secret for `user` (not yet enabled - a wrong or
    unconfirmed setup call must never lock anyone out of their account).
    Calling this again before /2fa/enable simply discards the previous,
    unconfirmed secret."""
    from app.utils.crypto import encrypt_secret
    from app.utils.totp import generate_qr_code_data_uri, generate_totp_secret, totp_provisioning_uri

    secret = generate_totp_secret()
    user.two_factor_secret = encrypt_secret(secret)
    db.commit()

    uri = totp_provisioning_uri(secret, user.email)
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_code_data_uri": generate_qr_code_data_uri(uri),
    }


def enable_two_factor(db: Session, user: User, code: str) -> dict:
    from app.utils.crypto import decrypt_secret
    from app.utils.totp import generate_backup_codes, hash_backup_codes, verify_totp_code

    if not user.two_factor_secret:
        raise HTTPException(status_code=400, detail="Start setup first with /auth/2fa/setup")
    if user.two_factor_enabled:
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled")

    secret = decrypt_secret(user.two_factor_secret)
    if not verify_totp_code(secret, code):
        raise HTTPException(status_code=400, detail="Incorrect code. Check your authenticator app and try again.")

    backup_codes = generate_backup_codes()
    user.two_factor_enabled = True
    user.two_factor_backup_codes = hash_backup_codes(backup_codes)
    log_audit(db, actor=user, action="enable_two_factor", entity_type="auth", entity_id=user.id)
    db.commit()

    return {"enabled": True, "backup_codes": backup_codes}


def disable_two_factor(db: Session, user: User, password: str) -> None:
    if not verify_password(password, user.password or ""):
        raise HTTPException(status_code=401, detail="Incorrect password")

    user.two_factor_enabled = False
    user.two_factor_secret = None
    user.two_factor_backup_codes = None
    log_audit(db, actor=user, action="disable_two_factor", entity_type="auth", entity_id=user.id)
    db.commit()


def verify_two_factor_login(db: Session, data, request=None) -> dict:
    from jose import JWTError, jwt
    from app.utils.crypto import decrypt_secret
    from app.utils.totp import verify_and_consume_backup_code, verify_totp_code

    try:
        claims = jwt.decode(data.pending_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="This verification step has expired. Please log in again.")
    if claims.get("token_type") != "2fa_pending":
        raise HTTPException(status_code=401, detail="Invalid verification token")

    user = db.query(User).filter(User.id == claims.get("user_id")).first()
    if not user or not user.two_factor_enabled:
        raise HTTPException(status_code=401, detail="Invalid verification token")

    secret = decrypt_secret(user.two_factor_secret)
    if verify_totp_code(secret, data.code):
        return _finalize_login(db, user, data, request=request)

    matched, remaining_json = verify_and_consume_backup_code(user.two_factor_backup_codes, data.code)
    if matched:
        user.two_factor_backup_codes = remaining_json
        db.commit()
        return _finalize_login(db, user, data, request=request)

    _record_login_history(db, data=data, email=user.email, status="failed", user=user, failure_reason="bad_2fa_code", request=request)
    db.commit()
    raise HTTPException(status_code=400, detail="Incorrect verification code")


def request_otp(db: Session, data):
    """Send a login OTP to the given email, creating a not-yet-active customer
    account if none exists (mirrors register_unified_user's create-now,
    activate-on-verification shape). Email-only for now - no SMS provider is
    wired into this backend."""
    email = data.email

    user = db.query(User).filter(User.email == email).first()
    if user and user.user_type != "CUSTOMER":
        raise HTTPException(status_code=400, detail="This email is registered under a different account type. Please use the standard login.")

    code, code_hash = create_otp_code()
    now = utcnow()

    if not user:
        role = db.query(Role).filter(Role.slug == "customer", Role.is_active == True).first()
        if not role:
            raise HTTPException(status_code=400, detail="Customer accounts are not available right now.")
        name = email.split("@", 1)[0]
        user = User(
            name=name,
            email=email,
            password=None,
            role_id=role.id,
            user_type="CUSTOMER",
            is_active=False,
            approval_status="NOT_REQUIRED",
            account_status="PENDING_OTP_VERIFICATION",
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.add(Customer(user_id=user.id, first_name=name, last_name="", full_name=name, email=email, status="inactive", email_verified=False))
        db.add(UserStatusHistory(user_id=user.id, to_status=user.account_status, reason="OTP login started"))

    user.otp_code_hash = code_hash
    user.otp_expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    user.otp_attempts = 0
    db.add(user)
    db.commit()
    db.refresh(user)

    subject, html = render_database_email(
        db,
        "otp_login",
        {"name": user.name, "email": user.email, "code": code},
        "Your Tourvaa verification code",
        otp_login_email(user.name, code),
    )
    try_send_email(user.email, subject, html, template_key="otp_login")
    return {"email": email, "expires_in_minutes": settings.OTP_EXPIRE_MINUTES}


def verify_otp_and_login(db: Session, data, request=None):
    email = data.email
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.otp_code_hash or not user.otp_expires_at:
        raise HTTPException(status_code=400, detail="Request a new verification code.")

    if user.otp_expires_at < utcnow():
        user.otp_code_hash = None
        user.otp_expires_at = None
        user.otp_attempts = 0
        db.commit()
        raise HTTPException(status_code=400, detail="This code has expired. Request a new one.")

    if hash_otp_code(data.code) != user.otp_code_hash:
        user.otp_attempts = (user.otp_attempts or 0) + 1
        if user.otp_attempts >= settings.OTP_MAX_ATTEMPTS:
            user.otp_code_hash = None
            user.otp_expires_at = None
            user.otp_attempts = 0
            db.commit()
            raise HTTPException(status_code=400, detail="Too many incorrect attempts. Request a new code.")
        db.commit()
        remaining = settings.OTP_MAX_ATTEMPTS - user.otp_attempts
        raise HTTPException(status_code=400, detail=f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} left.")

    user.otp_code_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0

    if user.account_status == "PENDING_OTP_VERIFICATION":
        user.account_status = "ACTIVE"
        user.is_active = True
        user.email_verified = True
        user.email_verified_at = utcnow()
        db.add(UserStatusHistory(user_id=user.id, from_status="PENDING_OTP_VERIFICATION", to_status="ACTIVE", reason="OTP verified"))
        customer = db.query(Customer).filter(Customer.user_id == user.id).first()
        if customer:
            customer.status = "active"
            customer.email_verified = True
    db.commit()
    db.refresh(user)

    return _finalize_login(db, user, data, request=request)


def refresh_user_token(db: Session, user: User, client_type: str | None = "web", device_id: str | None = None, session_id: str | None = None):
    auth_user = get_auth_user_payload(db, user)
    role_slug = auth_user["role"]["slug"]
    portal = get_portal_for_role(role_slug)
    token_claims = {
        "user_id": user.id,
        "email": user.email,
        "role": role_slug,
        "portal": portal,
        "client_type": client_type or "web",
        "device_id": device_id,
        "token_version": user.token_version,
        "session_id": session_id,
    }
    token = create_token(token_claims, portal=portal)
    refresh_token = create_token(
        token_claims,
        portal=portal,
        token_type="refresh",
        expires_minutes=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60,
    )

    return {
        "access_token": token,
        "_refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "client_type": client_type or "web",
        "user": auth_user,
    }


def verify_email(db: Session, token: str | None = ""):
    if not token:
        raise HTTPException(status_code=400, detail="Verification token is required")

    token_hash = hash_reset_token(token)
    user = db.query(User).filter(User.email_verification_token == token_hash).first()

    if not user or not user.email_verification_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    if user.email_verification_expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user.email_verified_at = utcnow()
    user.email_verified = True
    user_id_val = getattr(user, "id", None)
    customer = db.query(Customer).filter(Customer.user_id == user_id_val).first() if user_id_val else None
    if customer:
        customer.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires_at = None

    user_role = getattr(user, "role", None)
    role_slug = user_role.slug if user_role else ""
    user_id = getattr(user, "id", None)
    if user_id:
        if role_slug == "supplier":
            supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
            if supplier and supplier.approval_status in {"pending", "email_verification_pending"}:
                supplier.approval_status = "profile_incomplete"
                user.approval_status = "profile_incomplete"
                user.is_active = True
        elif role_slug == "agent-reseller":
            agent = db.query(Agent).filter(Agent.user_id == user.id).first()
            if agent and agent.approval_status in {"pending", "email_verification_pending"}:
                agent.approval_status = "profile_incomplete"
                user.approval_status = "profile_incomplete"
                user.is_active = True

    db.commit()
    return True


def get_login_history(db: Session, user: User, limit: int = 20):
    limit = max(1, min(limit, 100))
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "auth")
        .filter(AuditLog.action.in_(["login_success", "login_failed"]))
        .filter(AuditLog.actor_user_id == user.id)
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
    """Bumps token_version (invalidating every JWT already issued to this
    user) and revokes every active UserSession row. Delegates the actual
    revocation to services.sessions.force_logout_user so this and
    /sessions/users/{id}/force-logout can't diverge again -- they used to
    be two separate implementations, and this one alone never revoked
    sessions, leaving them "active" in the DB after /auth/logout."""
    from app.services.sessions import force_logout_user as _revoke_sessions
    old_version = target_user.token_version
    result = _revoke_sessions(db, target_user.id)
    log_audit(
        db,
        actor=actor,
        action="force_logout",
        entity_type="user",
        entity_id=target_user.id,
        old_values={"token_version": old_version},
        new_values={"token_version": result["token_version"]},
        request=request,
    )
    db.commit()
    db.refresh(target_user)
    return {"user_id": target_user.id, "token_version": target_user.token_version}


def forgot_password(db: Session, email: str, client_type: str | None = "web"):
    from fastapi import HTTPException

    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user:
        logger.info("Password reset requested for unknown email: %s", normalized_email)
        return False

    if settings.REQUIRE_EMAIL_VERIFICATION and user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER", "AFFILIATE"} and not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Email verification is required before password reset")

    if user.account_status != "ACTIVE" or not user.is_active:
        logger.info("Password reset skipped for inactive user id=%s", user.id)
        raise HTTPException(status_code=403, detail="Your account is inactive. Please contact support.")

    token, token_hash = create_password_reset_token()
    user.reset_password_token = token_hash
    user.reset_password_expires_at = utcnow() + timedelta(minutes=30)

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
            template_key="password_reset",
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

    if expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.account_status != "ACTIVE" or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    if settings.REQUIRE_EMAIL_VERIFICATION and user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER", "AFFILIATE"} and not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    user.password = hash_password(password)
    user.reset_password_token = None
    user.reset_password_expires_at = None
    user.token_version += 1

    db.commit()

    login_url = f"{settings.FRONTEND_URL}/login"
    try:
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
        try_send_email(user.email, subject, html, template_key="password_changed")
    except Exception as exc:
        logger.warning("Password changed email failed for user id=%s: %s", user.id, exc)

    return True


def validate_reset_token(db: Session, token: str):
    if not token:
        raise HTTPException(status_code=400, detail="Reset token is missing")

    token_hash = hash_reset_token(token)
    user = db.query(User).filter(User.reset_password_token == token_hash).first()

    if not user or not user.reset_password_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.reset_password_expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.account_status != "ACTIVE" or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    if settings.REQUIRE_EMAIL_VERIFICATION and user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER", "AFFILIATE"} and not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    return True






