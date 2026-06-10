from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.roles.models import Role
from app.config import settings
from app.modules.common.email_templates import (
    approved_email,
    password_reset_email,
    user_created_email,
)
from app.modules.common.mailer import send_email
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserUpdate
from app.security import create_password_reset_token, hash_password
from app.modules.auth.service import build_password_reset_url


APPROVAL_STATUSES = ["pending", "approved", "rejected"]


def serialize_user(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "profile_image": user.profile_image,
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
        "is_active": user.is_active,
        "approval_status": user.approval_status,
        "created_at": user.created_at,
    }


def get_all_users(db: Session):
    users = db.query(User).order_by(User.id.desc()).all()
    return [serialize_user(user) for user in users]


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


def create_user(db: Session, data: UserCreate):
    existing_user = db.query(User).filter(User.email == data.email).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    if data.role_id is not None:
        validate_role(db, data.role_id)

    user = User(
        name=data.name,
        email=data.email,
        phone=data.phone,
        profile_image=data.profile_image,
        address=data.address,
        country=data.country,
        state=data.state,
        city=data.city,
        pincode=data.pincode,
        password=hash_password(data.password),
        role_id=data.role_id,
        is_active=True,
        approval_status="approved",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    if data.password:
        send_email(
            user.email,
            "Your Tourvaa account is ready",
            user_created_email(
                user.name,
                user.email,
                data.password,
                f"{settings.FRONTEND_URL}/login",
            ),
        )

    return serialize_user(user)


def update_user(db: Session, user_id: int, data: UserUpdate):
    user = get_user_by_id(db, user_id)

    if data.name is not None:
        user.name = data.name

    if data.email is not None:
        existing_user = (
            db.query(User)
            .filter(User.email == data.email, User.id != user_id)
            .first()
        )

        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")

        user.email = data.email

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
            setattr(user, field, value)

    if data.role_id is not None:
        validate_role(db, data.role_id)
        user.role_id = data.role_id

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.approval_status is not None:
        if data.approval_status not in APPROVAL_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid approval status")

        if data.approval_status == "approved" and user.role_id is None:
            raise HTTPException(status_code=400, detail="Assign a role before approval")

        user.approval_status = data.approval_status
        user.is_active = data.approval_status == "approved"

    db.commit()
    db.refresh(user)

    send_email(
        user.email,
        "Your Tourvaa account is approved",
        approved_email(user.name, f"{settings.FRONTEND_URL}/login"),
    )

    return serialize_user(user)


def approve_user(db: Session, user_id: int, role_id: int | None = None):
    user = get_user_by_id(db, user_id)

    if role_id is not None:
        validate_role(db, role_id)
        user.role_id = role_id

    if user.role_id is None:
        raise HTTPException(status_code=400, detail="Assign a role before approval")

    user.approval_status = "approved"
    user.is_active = True

    db.commit()
    db.refresh(user)

    return serialize_user(user)


def reject_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)
    user.approval_status = "rejected"
    user.is_active = False

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


def delete_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)

    db.delete(user)
    db.commit()

    return True
