from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.roles.models import Role
from app.config import settings
from app.modules.common.email_templates import (
    approved_email,
    password_reset_email,
)
from app.modules.common.mailer import send_email, try_send_email
from app.modules.audit.service import log_audit
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserCreate, UserUpdate
from app.security import create_password_reset_token, hash_password
from app.modules.auth.service import build_password_reset_url
from app.modules.common.media import existing_storage_path


APPROVAL_STATUSES = ["pending", "approved", "rejected"]


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
        "created_at": user.created_at,
    }


def get_all_users(db: Session, page: int | None = None, limit: int | None = None, search: str = ""):
    query = db.query(User)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
                User.phone.ilike(pattern),
            )
        )

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
    user = db.query(User).filter(User.id == user_id).first()

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
    try_send_email(
        user.email,
        "Set up your Tourvaa password",
        password_reset_email(user.name, reset_url),
    )

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
    was_approved = user.approval_status == "approved"

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

    if data.is_active is not None:
        ensure_not_removing_last_super_admin(db, user, new_is_active=data.is_active)
        if user.is_active != data.is_active:
            user.token_version += 1
        user.is_active = data.is_active

    if data.approval_status is not None:
        if data.approval_status not in APPROVAL_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid approval status")

        if data.approval_status == "approved" and user.role_id is None:
            raise HTTPException(status_code=400, detail="Assign a role before approval")

        ensure_not_removing_last_super_admin(
            db,
            user,
            new_role_id=new_role_id,
            new_approval_status=data.approval_status,
        )
        if user.approval_status != data.approval_status:
            user.token_version += 1
        new_active = data.approval_status == "approved"
        if user.is_active != new_active:
            user.token_version += 1
        user.approval_status = data.approval_status
        user.is_active = new_active

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

    if data.approval_status == "approved" and not was_approved:
        try_send_email(
            user.email,
            "Your Tourvaa account is approved",
            approved_email(user.name, f"{settings.FRONTEND_URL}/login"),
        )

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
    was_approved = user.approval_status == "approved"

    if role_id is not None:
        validate_role(db, role_id)
        user.role_id = role_id
        sync_user_roles(db, user, [role_id])

    if user.role_id is None:
        raise HTTPException(status_code=400, detail="Assign a role before approval")

    user.approval_status = "approved"
    user.is_active = True
    user.token_version += 1

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

    if not was_approved:
        try_send_email(
            user.email,
            "Your Tourvaa account is approved",
            approved_email(user.name, f"{settings.FRONTEND_URL}/login"),
        )

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


def reject_user(
    db: Session,
    user_id: int,
    actor: User | None = None,
    request: Request | None = None,
):
    user = get_user_by_id(db, user_id)
    ensure_not_removing_last_super_admin(db, user, new_approval_status="rejected")
    old_values = serialize_user(user)
    user.approval_status = "rejected"
    user.is_active = False
    user.token_version += 1

    log_audit(
        db,
        actor=actor,
        action="reject_user",
        entity_type="user",
        entity_id=user.id,
        old_values=old_values,
        new_values=serialize_user(user),
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
