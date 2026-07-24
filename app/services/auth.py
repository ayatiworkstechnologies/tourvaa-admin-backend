from datetime import datetime, timedelta
import logging
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.utils.email_templates import (
    render_database_email,
    password_changed_email,
    password_reset_email,
    email_verification_email,
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
from app.models.sessions import LoginHistory
from app.services.sessions import create_session
from app.utils.media import existing_storage_path
from app.auth.security import (
    create_password_reset_token,
    create_token,
    get_portal_for_role,
    hash_password,
    hash_reset_token,
    verify_password,
)

logger = logging.getLogger(__name__)
PUBLIC_REGISTRATION_ROLES = {"customer", "supplier", "agent-reseller"}


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
    try_send_email(user.email, subject, html)


def register_unified_user(db: Session, data):
    email = str(data.email).strip().lower()
    phone = f"{data.country_code}{data.mobile_number}"
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    if db.query(User).filter(or_(User.mobile_number == phone, User.phone == phone)).first():
        raise HTTPException(status_code=400, detail="Mobile number already exists")

    role_slug = {"CUSTOMER": "customer", "AGENT": "agent-reseller", "SUPPLIER": "supplier"}[data.account_type]
    role = db.query(Role).filter(Role.slug == role_slug, Role.is_active == True).first()
    if not role:
        raise HTTPException(status_code=400, detail="Selected account type is not available")

    now = datetime.utcnow()
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
        approval_status="PENDING" if data.account_type == "SUPPLIER" else "NOT_REQUIRED",
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
    else:
        db.add(Agent(user_id=user.id, agent_name=user.name, status="inactive", approval_status="NOT_REQUIRED"))

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
    if user.email_verification_expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if user.account_status not in {"PENDING_EMAIL_VERIFICATION", "PENDING_PASSWORD_CREATION"}:
        raise HTTPException(status_code=400, detail="Verification link has already been used")
    return user


def complete_registration(db: Session, token: str, password: str):
    user = _registration_token_user(db, token)
    old_status = user.account_status
    now = datetime.utcnow()
    user.password = hash_password(password)
    user.password_created_at = now
    user.email_verified = True
    user.email_verified_at = now
    user.email_verification_token = None
    user.email_verification_expires_at = None
    user.account_status = "ACTIVE"
    user.is_active = True
    user.approval_status = "PENDING" if user.user_type == "SUPPLIER" else "NOT_REQUIRED"

    customer = db.query(Customer).filter(Customer.user_id == user.id).first()
    if customer:
        customer.email_verified = True
        customer.status = "active"

    agent = db.query(Agent).filter(Agent.user_id == user.id).first()
    if agent:
        agent.status = "active"
        agent.approval_status = "NOT_REQUIRED"
        agent.approved_at = None
        agent.rejection_reason = None

    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if supplier:
        supplier.status = "active"
        supplier.approval_status = "PENDING"
        supplier.approved_at = None
        supplier.rejection_reason = None

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
    db.commit()
    login_url = build_portal_login_url(user)
    try:
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
        try_send_email(user.email, subject, html)
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
    user.email_verification_expires_at = datetime.utcnow() + timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
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
    user.email_verification_expires_at = datetime.utcnow() + timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
    db.commit()
    send_email_verification(db, user, token, redirect)
    return user



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

        if selected_role.slug not in PUBLIC_REGISTRATION_ROLES:
            raise HTTPException(status_code=403, detail="Selected role is not available for registration")

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

    role_slug = selected_role.slug if selected_role else None
    supplier_verification = role_slug == "supplier"
    verification_token = None
    verification_token_hash = None
    if supplier_verification:
        verification_token, verification_token_hash = create_password_reset_token()
    now = datetime.utcnow()

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
        user_type={"customer": "CUSTOMER", "supplier": "SUPPLIER", "agent-reseller": "AGENT"}.get(selected_role.slug if selected_role else "", "ADMIN"),
        is_active=not supplier_verification,
        approval_status="pending" if supplier_verification else "approved",
        account_status="PENDING_EMAIL_VERIFICATION" if supplier_verification else "ACTIVE",
        admin_verified=False,
        admin_verified_at=None,
        email_verified=False,
        password_created_at=now,
        email_verified_at=None,
        email_verification_token=verification_token_hash,
        email_verification_expires_at=(
            now + timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES)
            if supplier_verification else None
        ),
    )

    db.add(new_user)
    db.flush()
    if new_user.role_id:
        db.add(UserRole(user_id=new_user.id, role_id=new_user.role_id))

    # Auto-create the corresponding profile record linked by user_id
    if role_slug == "customer":
        existing_customer = db.query(Customer).filter(Customer.email == email).first()
        if not existing_customer:
            name_parts = new_user.name.strip().split(None, 1)
            first = name_parts[0] if name_parts else ""
            last = name_parts[1] if len(name_parts) > 1 else ""
            db.add(Customer(
                user_id=new_user.id,
                first_name=first,
                last_name=last,
                full_name=new_user.name.strip(),
                email=email,
                phone=new_user.phone,
                status="active",
                email_verified=False,
            ))
        else:
            existing_customer.user_id = new_user.id

    elif role_slug == "supplier":
        existing_supplier = db.query(Supplier).filter(Supplier.user_id == new_user.id).first()
        if not existing_supplier:
            db.add(Supplier(
                user_id=new_user.id,
                supplier_name=new_user.name.strip(),
                status="inactive",
                approval_status="email_verification_pending",
            ))

    elif role_slug == "agent-reseller":
        existing_agent = db.query(Agent).filter(Agent.user_id == new_user.id).first()
        if not existing_agent:
            db.add(Agent(
                user_id=new_user.id,
                agent_name=new_user.name.strip(),
                status="active",
                approval_status="approved",
                approved_at=now,
            ))

    db.commit()
    db.refresh(new_user)

    if supplier_verification and verification_token:
        send_email_verification(db, new_user, verification_token)

    return new_user


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

    if not user.password or not verify_password(data.password, user.password):
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

    if settings.REQUIRE_EMAIL_VERIFICATION and user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER"} and not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Email verification is required before login")

    auth_user = get_auth_user_payload(db, user)
    role_slug = auth_user["role"]["slug"]
    portal = get_portal_for_role(role_slug)

    token = create_token({
        "user_id": user.id,
        "email": user.email,
        "role": role_slug,
        "portal": portal,
        "client_type": data.client_type or "web",
        "device_id": data.device_id,
        "token_version": user.token_version,
    }, portal=portal)

    if user.account_status != "ACTIVE" or not user.is_active:
        _record_login_history(db, data=data, email=email, status="restricted", user=user, failure_reason=user.account_status, request=request)
        db.commit()
        if user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER"}:
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

    refresh_token = create_token({
        "user_id": user.id,
        "email": user.email,
        "role": role_slug,
        "portal": portal,
        "client_type": data.client_type or "web",
        "device_id": data.device_id,
        "token_version": user.token_version,
    }, portal=portal, token_type="refresh", expires_minutes=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)

    try:
        session = create_session(db, user, request=request)
        _record_login_history(
            db,
            data=data,
            email=email,
            status="success",
            user=user,
            session_id=session.session_id,
            request=request,
        )
    except Exception as error:
        logger.warning("Login session tracking failed for user %s: %s", user.id, error)
        session = None

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
    user.last_login_at = datetime.utcnow()
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


def refresh_user_token(db: Session, user: User, client_type: str | None = "web", device_id: str | None = None):
    auth_user = get_auth_user_payload(db, user)
    role_slug = auth_user["role"]["slug"]
    portal = get_portal_for_role(role_slug)
    token = create_token({
        "user_id": user.id,
        "email": user.email,
        "role": role_slug,
        "portal": portal,
        "client_type": client_type or "web",
        "device_id": device_id,
        "token_version": user.token_version,
    }, portal=portal)
    refresh_token = create_token({
        "user_id": user.id,
        "email": user.email,
        "role": role_slug,
        "portal": portal,
        "client_type": client_type or "web",
        "device_id": device_id,
        "token_version": user.token_version,
    }, portal=portal, token_type="refresh", expires_minutes=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)

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

    if user.email_verification_expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user.email_verified_at = datetime.utcnow()
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
    from fastapi import HTTPException

    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user:
        logger.info("Password reset requested for unknown email: %s", normalized_email)
        return False

    if settings.REQUIRE_EMAIL_VERIFICATION and user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER"} and not user.email_verified_at:
        raise HTTPException(status_code=403, detail="Email verification is required before password reset")

    if user.account_status != "ACTIVE" or not user.is_active:
        logger.info("Password reset skipped for inactive user id=%s", user.id)
        raise HTTPException(status_code=403, detail="Your account is inactive. Please contact support.")

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

    if user.account_status != "ACTIVE" or not user.is_active or not user.email_verified:
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
        try_send_email(user.email, subject, html)
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

    if user.reset_password_expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if user.account_status != "ACTIVE" or not user.is_active or not user.email_verified:
        raise HTTPException(status_code=403, detail="Account is not eligible for password reset")

    return True






