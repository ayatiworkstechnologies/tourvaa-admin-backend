from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.permissions import require_permission
from app.utils.pagination import pagination_params
from app.models.users import User
from app.schemas.users import UserApprovalUpdate, UserCreate, UserDeactivationUpdate, UserRolesUpdate, UserUpdate
from app.services.users import (
    get_all_users,
    get_user_detail,
    create_user,
    update_user,
    delete_user,
    approve_user,
    deactivate_user,
    send_user_password_reset,
    assign_roles_to_user,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/")
def list_users(
    account_status: str = Query(default=""),
    user_type: str = Query(default=""),
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-users")),
):
    paginated = get_all_users(
        db,
        page=params["page"],
        limit=params["limit"],
        search=params["search"],
        account_status=account_status,
        user_type=user_type,
    )

    return {
        "status": "success",
        "data": paginated["items"],
        **paginated,
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("create-users")),
):
    user = create_user(db, data, actor=current_user, request=request)

    return {
        "status": "success",
        "message": "User created successfully",
        "data": user
    }


@router.put("/{user_id}")
def edit_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-users")),
):
    user = update_user(db, user_id, data, actor=current_user, request=request)

    return {
        "status": "success",
        "message": "User updated successfully",
        "data": user
    }


@router.delete("/{user_id}")
def remove_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("delete-users")),
):
    delete_user(db, user_id, actor=current_user, request=request)

    return {
        "status": "success",
        "message": "User deleted successfully"
    }


@router.post("/{user_id}/activate")
def activate_user_account(
    user_id: int,
    data: UserApprovalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-users")),
):
    return {"status": "success", "message": "User activated successfully", "data": approve_user(db, user_id, data.role_id, actor=current_user, request=request)}


@router.post("/{user_id}/deactivate")
def deactivate_user_account(
    user_id: int,
    data: UserDeactivationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-users")),
):
    return {"status": "success", "message": "User deactivated successfully", "data": deactivate_user(db, user_id, data.reason, actor=current_user, request=request)}


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


@router.post("/{user_id}/roles")
def assign_user_roles(
    user_id: int,
    data: UserRolesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-users")),
):
    user = assign_roles_to_user(
        db,
        user_id,
        data.role_ids,
        actor=current_user,
        request=request,
    )

    return {
        "status": "success",
        "message": "Roles assigned successfully",
        "data": user,
    }
