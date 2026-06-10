from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.modules.common.auth import require_permission
from app.modules.users.schemas import UserApprovalUpdate, UserCreate, UserUpdate
from app.modules.users.service import (
    get_all_users,
    get_user_detail,
    create_user,
    update_user,
    delete_user,
    approve_user,
    reject_user,
    send_user_password_reset,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/")
def list_users(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-users")),
):
    users = get_all_users(db)

    return {
        "status": "success",
        "data": users
    }


@router.get("/{user_id}")
def user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-users")),
):
    user = get_user_detail(db, user_id)

    return {
        "status": "success",
        "data": user
    }


@router.post("/")
def add_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("create-users")),
):
    user = create_user(db, data)

    return {
        "status": "success",
        "message": "User created successfully",
        "data": user
    }


@router.put("/{user_id}")
def edit_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-users")),
):
    user = update_user(db, user_id, data)

    return {
        "status": "success",
        "message": "User updated successfully",
        "data": user
    }


@router.delete("/{user_id}")
def remove_user(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("delete-users")),
):
    delete_user(db, user_id)

    return {
        "status": "success",
        "message": "User deleted successfully"
    }


@router.post("/{user_id}/approve")
def approve_pending_user(
    user_id: int,
    data: UserApprovalUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-users")),
):
    user = approve_user(db, user_id, data.role_id)

    return {
        "status": "success",
        "message": "User approved successfully",
        "data": user
    }


@router.post("/{user_id}/reject")
def reject_pending_user(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-users")),
):
    user = reject_user(db, user_id)

    return {
        "status": "success",
        "message": "User rejected successfully",
        "data": user
    }


@router.post("/{user_id}/send-reset-mail")
def send_reset_mail(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-users")),
):
    user = send_user_password_reset(db, user_id)

    return {
        "status": "success",
        "message": "Password reset email sent successfully",
        "data": user
    }
