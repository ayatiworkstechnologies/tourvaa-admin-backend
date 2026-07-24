from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.roles import Role
from app.config import settings
from app.utils.email_templates import (
    approved_email,
    base_email,
    esc,
    password_reset_email,
    render_database_email,
    user_created_email,
)
from app.utils.mailer import send_email, try_send_email
from app.services.audit import AuditLog, log_audit
from app.models.users import User, UserRole, UserStatusHistory
from app.schemas.users import UserCreate, UserUpdate
from app.auth.security import create_password_reset_token, hash_password
from app.services.auth import build_password_reset_url
from app.utils.media import existing_storage_path


def serialize_user(user: User):
    roles = [
        {
            "id": user_role.role.id,
            "name": user_role.role.name,
            "slug": user_role.role.slug,
            "is_active": user_role.role.is_active,
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
        "address": user.address,
        "country": user.country,
        "state": user.state,
        "city": user.city,
        "pincode": user.pincode,
        "role_id": user.role_id,
        "role": {
            "id": user.role.id,
            "name": user.role.name,
            "slug": user.role.slug,
            "is_active": user.role.is_active,
        } if user.role else None,
        "roles": roles,
        "is_active": user.is_active,
        "token_version": user.token_version,
        "approval_status": user.approval_status,
        "user_type": user.user_type,
        "country_code": user.country_code,
        "mobile_number": user.mobile_number,
        "email_verified": user.email_verified,
        "password_created": bool(user.password_created_at),
        "account_status": user.account_status,
        "admin_verified": user.admin_verified,
        "admin_verified_at": user.admin_verified_at,
        "admin_verified_by": user.admin_verified_by,
        "deactivated_at": user.deactivated_at,
        "deactivated_by": user.deactivated_by,
        "deactivation_reason": user.deactivation_reason,
        "last_login_at": user.last_login_at,
        "updated_at": user.updated_at,
        "status_history": [
            {
                "id": entry.id,
                "from_status": entry.from_status,
                "to_status": entry.to_status,
                "reason": entry.reason,
                "changed_by": entry.changed_by,
                "created_at": entry.created_at,
            }
            for entry in sorted(user.status_history, key=lambda item: item.id, reverse=True)
        ],
        "created_at": user.created_at,
    }


def get_all_users(db: Session, page: int | None = None, limit: int | None = None, search: str = "", account_status: str = "", user_type: str = ""):
    query = db.query(User).options(
        joinedload(User.role),
        selectinload(User.user_roles).joinedload(UserRole.role),
        selectinload(User.status_history),
    )

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
                User.phone.ilike(pattern),
            )
        )
    if account_status:
        query = query.filter(User.account_status == account_status.upper())
    if user_type:
        query = query.filter(User.user_type == user_type.upper())

    query = query.order_by(User.id.desc())

    if page is None or limit is None:
        users = query.all()
        return [serialize_user(user) for user in users]

    total = query.count()
    users = query.offset((page - 1) * limit).limit(limit).all()
    return {
        "items": [serialize_user(user) for user in users],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


def get_user_by_id(db: Session, user_id: int):
    user = (
        db.query(User)
        .options(
            joinedload(User.role),
            selectinload(User.user_roles).joinedload(UserRole.role),
            selectinload(User.status_history),
        )
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def get_user_detail(db: Session, user_id: int):
    return serialize_user(get_user_by_id(db, user_id))


def validate_role(db: Session, role_id: int):
    role = (
        db.query(Role)
        .filter(Role.id == role_id)
        .filter(Role.is_active == True)
        .first()
    )

    if not role:
        raise HTTPException(status_code=400, detail="Selected role is not available")

    return role


def sync_user_roles(db: Session, user: User, role_ids: list[int]):
    unique_role_ids = list(dict.fromkeys(role_ids))

    if user.role_id and user.role_id not in unique_role_ids:
        unique_role_ids.insert(0, user.role_id)

    roles = []
    for role_id in unique_role_ids:
        roles.append(validate_role(db, role_id))

    db.query(UserRole).filter(UserRole.user_id == user.id).delete()

    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))

    return roles


def is_super_admin(user: User):
    if user.role and user.role.slug == "super-admin":
        return True

    return any(user_role.role and user_role.role.slug == "super-admin" for user_role in user.user_roles)


def count_active_super_admins(db: Session):
    return (
        db.query(User)
        .outerjoin(UserRole, UserRole.user_id == User.id)
        .outerjoin(Role, (Role.id == User.role_id) | (Role.id == UserRole.role_id))
        .filter(Role.slug == "super-admin")
        .filter(User.is_active == True)
        .filter(User.approval_status == "approved")
        .distinct()
        .count()
    )


def ensure_not_removing_last_super_admin(
    db: Session,
    user: User,
    *,
    new_role_id: int | None | object = None,
    new_is_active: bool | None = None,
    new_approval_status: str | None = None,
):
    if not is_super_admin(user):
        return

    removing_super_admin_role = False

    if new_role_id is not None:
        new_role = db.query(Role).filter(Role.id == new_role_id).first()
        removing_super_admin_role = not new_role or new_role.slug != "super-admin"

    disabling = new_is_active is False
    unapproving = new_approval_status in {"pending", "rejected"}

    if removing_super_admin_role or disabling or unapproving:
        if count_active_super_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last active super admin")


def create_user(
    db: Session,
    data: UserCreate,
    actor: User | None = None,
    request: Request | None = None,
):
    email = str(data.email).strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    if data.role_id is not None:
        validate_role(db, data.role_id)

    token, token_hash = create_password_reset_token()
    user = User(
        name=data.name.strip(),
        email=email,
        phone=data.phone.strip(),
        profile_image=data.profile_image.strip(),
        address=data.address.strip(),
        country=data.country.strip(),
        state=data.state.strip(),
        city=data.city.strip(),
        pincode=data.pincode.strip(),
        password=hash_password(create_password_reset_token()[0]),
        role_id=data.role_id,
        is_active=True,
        approval_status="approved",
        reset_password_token=token_hash,
        reset_password_expires_at=datetime.utcnow() + timedelta(minutes=30),
    )

    db.add(user)
    db.flush()
    if user.role_id:
        sync_user_roles(db, user, [user.role_id])

    log_audit(
        db,
        actor=actor,
        action="create_user",
        entity_type="user",
        entity_id=user.id,
        new_values=serialize_user(user),
        request=request,
    )
    db.commit()
    db.refresh(user)

    reset_url = build_password_reset_url(token)
    subject, html = render_database_email(
        db, "user_created",
        {"name": user.name, "email": user.email, "set_password_url": reset_url},
        "Your Tourvaa account is ready",
        user_created_email(user.name, user.email, reset_url),
    )
    try_send_email(user.email, subject, html)

    return serialize_user(user)


def update_user(
    db: Session,
    user_id: int,
    data: UserUpdate,
    actor: User | None = None,
    request: Request | None = None,
):
    user = get_user_by_id(db, user_id)
    old_values = serialize_user(user)

    if data.name is not None:
        user.name = data.name.strip()

    if data.email is not None:
        email = str(data.email).strip().lower()
        existing_user = (
            db.query(User)
            .filter(User.email == email, User.id != user_id)
            .first()
        )

        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")

        user.email = email

    for field in [
        "phone",
        "profile_image",
        "address",
        "country",
        "state",
        "city",
        "pincode",
    ]:
        value = getattr(data, field)
        if value is not None:
            setattr(user, field, value.strip())

    new_role_id = None
    if data.role_id is not None:
        validate_role(db, data.role_id)
        ensure_not_removing_last_super_admin(db, user, new_role_id=data.role_id)
        if user.role_id != data.role_id:
            user.token_version += 1
        user.role_id = data.role_id
        sync_user_roles(db, user, [data.role_id])
        new_role_id = data.role_id

    log_audit(
        db,
        actor=actor,
        action="update_user",
        entity_type="user",
        entity_id=user.id,
        old_values=old_values,
        new_values=serialize_user(user),
        request=request,
    )
    db.commit()
    db.refresh(user)

    return serialize_user(user)


def approve_user(
    db: Session,
    user_id: int,
    role_id: int | None = None,
    actor: User | None = None,
    request: Request | None = None,
):
    user = get_user_by_id(db, user_id)
    old_values = serialize_user(user)
    if user.account_status == "ACTIVE" and user.is_active:
        raise HTTPException(status_code=400, detail="User account is already active")

    if role_id is not None:
        validate_role(db, role_id)
        user.role_id = role_id
        sync_user_roles(db, user, [role_id])

    if user.role_id is None:
        raise HTTPException(status_code=400, detail="Assign a role before approval")
    if user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER"} and (not user.email_verified or not user.password_created_at):
        raise HTTPException(status_code=400, detail="Email verification and password creation must be completed before activation")

    old_status = user.account_status
    user.approval_status = "approved"
    user.is_active = True
    user.account_status = "ACTIVE"
    user.admin_verified = True
    user.admin_verified_at = datetime.utcnow()
    user.admin_verified_by = actor.id if actor else None
    user.deactivated_at = None
    user.deactivated_by = None
    user.deactivation_reason = None
    db.add(UserStatusHistory(user_id=user.id, from_status=old_status, to_status="ACTIVE", reason="Activated by administrator", changed_by=actor.id if actor else None))
    role_slug = user.role.slug if user.role else ""
    if role_slug == "customer":
        from app.models.customers import Customer
        profile = db.query(Customer).filter(Customer.user_id == user.id).first()
        if profile:
            profile.status = "active"
    elif role_slug == "supplier":
        from app.models.suppliers import Supplier
        profile = db.query(Supplier).filter(Supplier.user_id == user.id).first()
        if profile:
            profile.status = "active"
            profile.approval_status = "approved"
    elif role_slug == "agent-reseller":
        from app.models.agents import Agent
        profile = db.query(Agent).filter(Agent.user_id == user.id).first()
        if profile:
            profile.status = "active"
            profile.approval_status = "approved"

    log_audit(
        db,
        actor=actor,
        action="approve_user",
        entity_type="user",
        entity_id=user.id,
        old_values=old_values,
        new_values=serialize_user(user),
        request=request,
    )
    db.commit()
    db.refresh(user)

    login_url = f"{settings.FRONTEND_URL}/login"
    subject, html = render_database_email(
        db, "account_approved",
        {"name": user.name, "login_url": login_url},
        "Your Tourvaa account is active",
        approved_email(user.name, login_url),
    )
    try_send_email(user.email, subject, html)

    return serialize_user(user)


def deactivate_user(db: Session, user_id: int, reason: str, actor: User | None = None, request: Request | None = None):
    user = get_user_by_id(db, user_id)
    ensure_not_removing_last_super_admin(db, user, new_is_active=False)
    old_values = serialize_user(user)
    old_status = user.account_status
    user.account_status = "INACTIVE"
    user.is_active = False
    user.deactivated_at = datetime.utcnow()
    user.deactivated_by = actor.id if actor else None
    user.deactivation_reason = reason.strip()
    user.token_version += 1
    role_slug = user.role.slug if user.role else ""
    if role_slug == "customer":
        from app.models.customers import Customer
        profile = db.query(Customer).filter(Customer.user_id == user.id).first()
    elif role_slug == "supplier":
        from app.models.suppliers import Supplier
        profile = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    elif role_slug == "agent-reseller":
        from app.models.agents import Agent
        profile = db.query(Agent).filter(Agent.user_id == user.id).first()
    else:
        profile = None
    if profile:
        profile.status = "inactive"
    db.add(UserStatusHistory(user_id=user.id, from_status=old_status, to_status="INACTIVE", reason=reason.strip(), changed_by=actor.id if actor else None))
    log_audit(db, actor=actor, action="deactivate_user", entity_type="user", entity_id=user.id, old_values=old_values, new_values=serialize_user(user), request=request)
    db.commit()
    db.refresh(user)
    try_send_email(user.email, "Your Tourvaa account is inactive", base_email("Account deactivated", f"Hi {esc(user.name)},", f"Your Tourvaa account has been deactivated.<br /><br />Reason: {esc(reason)}"))
    return serialize_user(user)


def reactivate_user(
    db: Session,
    user_id: int,
    actor: User | None = None,
    request: Request | None = None,
):
    """Restore a previously deactivated account without changing role approval."""
    user = get_user_by_id(db, user_id)
    if user.account_status == "ACTIVE" and user.is_active:
        raise HTTPException(status_code=400, detail="User account is already active")

    if user.user_type in {"CUSTOMER", "AGENT", "SUPPLIER"}:
        if not user.password_created_at:
            raise HTTPException(
                status_code=400,
                detail="Password creation must be completed before reactivation",
            )
        if not user.email_verified or not user.email_verified_at:
            raise HTTPException(
                status_code=400,
                detail="Email verification must be completed before reactivation",
            )

    old_values = serialize_user(user)
    old_status = user.account_status
    user.account_status = "ACTIVE"
    user.is_active = True
    user.admin_verified = True
    user.admin_verified_at = datetime.utcnow()
    user.admin_verified_by = actor.id if actor else None
    user.deactivated_at = None
    user.deactivated_by = None
    user.deactivation_reason = None
    user.token_version += 1

    role_slug = user.role.slug if user.role else ""
    if role_slug == "customer":
        from app.models.customers import Customer
        profile = db.query(Customer).filter(Customer.user_id == user.id).first()
    elif role_slug == "supplier":
        from app.models.suppliers import Supplier
        profile = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    elif role_slug == "agent-reseller":
        from app.models.agents import Agent
        profile = db.query(Agent).filter(Agent.user_id == user.id).first()
    else:
        profile = None

    if profile:
        profile.status = "active"

    db.add(
        UserStatusHistory(
            user_id=user.id,
            from_status=old_status,
            to_status="ACTIVE",
            reason="Reactivated by administrator",
            changed_by=actor.id if actor else None,
        )
    )
    log_audit(
        db,
        actor=actor,
        action="reactivate_user",
        entity_type="user",
        entity_id=user.id,
        old_values=old_values,
        new_values=serialize_user(user),
        request=request,
    )
    db.commit()
    db.refresh(user)

    login_url = f"{settings.FRONTEND_URL}/login"
    subject, html = render_database_email(
        db,
        "account_reactivated",
        {"name": user.name, "login_url": login_url},
        "Your Tourvaa account is active again",
        approved_email(user.name, login_url),
    )
    try_send_email(user.email, subject, html)
    return serialize_user(user)


def assign_roles_to_user(
    db: Session,
    user_id: int,
    role_ids: list[int],
    actor: User | None = None,
    request: Request | None = None,
):
    user = get_user_by_id(db, user_id)

    if not role_ids:
        raise HTTPException(status_code=400, detail="At least one role is required")

    old_values = serialize_user(user)
    new_primary_role_id = role_ids[0]
    if is_super_admin(user):
        keeps_super_admin = (
            db.query(Role)
            .filter(Role.id.in_(role_ids))
            .filter(Role.slug == "super-admin")
            .first()
        )
        if not keeps_super_admin and count_active_super_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last active super admin")

    roles = sync_user_roles(db, user, role_ids)

    if user.role_id != new_primary_role_id:
        user.token_version += 1

    user.role_id = new_primary_role_id

    log_audit(
        db,
        actor=actor,
        action="assign_user_roles",
        entity_type="user",
        entity_id=user.id,
        old_values=old_values,
        new_values={"role_ids": [role.id for role in roles]},
        request=request,
    )
    db.commit()
    db.refresh(user)

    return serialize_user(user)


def send_user_password_reset(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)
    token, token_hash = create_password_reset_token()

    user.reset_password_token = token_hash
    user.reset_password_expires_at = datetime.utcnow() + timedelta(minutes=30)
    db.commit()

    reset_url = build_password_reset_url(token)
    send_email(
        user.email,
        "Reset your Tourvaa password",
        password_reset_email(user.name, reset_url),
    )

    return serialize_user(user)


def delete_user(
    db: Session,
    user_id: int,
    actor: User | None = None,
    request: Request | None = None,
):
    user = get_user_by_id(db, user_id)

    if actor and actor.id == user.id:
        raise HTTPException(status_code=400, detail="Users cannot delete themselves")

    ensure_not_removing_last_super_admin(
        db,
        user,
        new_is_active=False,
        new_approval_status="rejected",
    )
    old_values = serialize_user(user)

    from app.models.agents import Agent, AgentDocument
    from app.models.affiliates import Affiliate, AffiliateDocument
    from app.models.affiliate_tracking import AffiliatePayout
    from app.models.bookings import Booking, BookingCommunication, BookingStatusHistory, MessageReply
    from app.models.cancellations import CancellationRequest
    from app.models.checkout import CheckoutSession
    from app.models.cms import Tour
    from app.models.customers import Customer, CustomerCancellationRequest, CustomerCommunication
    from app.models.invoices import Invoice
    from app.models.notifications import Notification, PushSubscription
    from app.models.payments import Payment, PaymentTransaction
    from app.models.suppliers import (
        Supplier,
        SupplierApprovalHistory,
        SupplierDocument,
        SupplierVehicle,
    )
    from app.models.supplier_ledger import SupplierPayout
    from app.models.tour_versions import TourVersion
    from app.models.website_cms import Blog

    def nullify_reference(model, column):
        db.query(model).filter(column == user_id).update(
            {column.key: None},
            synchronize_session=False,
        )

    for model, column in [
        (User, User.admin_verified_by),
        (User, User.deactivated_by),
        (UserStatusHistory, UserStatusHistory.changed_by),
        (Customer, Customer.user_id),
        (Customer, Customer.blocked_by),
        (CustomerCommunication, CustomerCommunication.sent_by_user_id),
        (CustomerCancellationRequest, CustomerCancellationRequest.reviewed_by),
        (Agent, Agent.user_id),
        (Agent, Agent.approved_by),
        (Agent, Agent.rejected_by),
        (AgentDocument, AgentDocument.reviewed_by),
        (Supplier, Supplier.user_id),
        (Supplier, Supplier.approved_by),
        (Supplier, Supplier.rejected_by),
        (SupplierApprovalHistory, SupplierApprovalHistory.changed_by),
        (SupplierVehicle, SupplierVehicle.reviewed_by),
        (SupplierDocument, SupplierDocument.reviewed_by),
        (Affiliate, Affiliate.user_id),
        (Affiliate, Affiliate.approved_by),
        (Affiliate, Affiliate.rejected_by),
        (AffiliateDocument, AffiliateDocument.reviewed_by),
        (AffiliatePayout, AffiliatePayout.initiated_by),
        (CheckoutSession, CheckoutSession.user_id),
        (Booking, Booking.created_by),
        (Booking, Booking.booked_by_user_id),
        (Booking, Booking.cancelled_by),
        (BookingStatusHistory, BookingStatusHistory.changed_by_user_id),
        (BookingCommunication, BookingCommunication.sender_user_id),
        (MessageReply, MessageReply.sender_user_id),
        (CancellationRequest, CancellationRequest.reviewed_by),
        (Payment, Payment.created_by),
        (PaymentTransaction, PaymentTransaction.created_by),
        (Tour, Tour.created_by),
        (Tour, Tour.updated_by),
        (Invoice, Invoice.created_by),
        (Notification, Notification.user_id),
        (PushSubscription, PushSubscription.user_id),
        (SupplierPayout, SupplierPayout.initiated_by),
        (SupplierPayout, SupplierPayout.approved_by),
        (TourVersion, TourVersion.submitted_by),
        (TourVersion, TourVersion.reviewed_by),
        (Blog, Blog.created_by),
        (AuditLog, AuditLog.actor_user_id),
    ]:
        nullify_reference(model, column)

    db.delete(user)
    log_audit(
        db,
        actor=actor,
        action="delete_user",
        entity_type="user",
        entity_id=user_id,
        old_values=old_values,
        request=request,
    )
    db.commit()

    return True
