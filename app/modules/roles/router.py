from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_permission
from app.modules.common.pagination import pagination_params
from app.modules.users.models import User
from app.modules.roles.schemas import RoleCreate, RoleUpdate, AssignPermissions
from app.modules.roles.service import (
    get_roles,
    get_role,
    create_role,
    update_role,
    delete_role,
    assign_permissions_to_role,
    get_role_permissions,
)

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("/public/options")
def public_role_options(db: Session = Depends(get_db)):
    public_role_slugs = {"customer", "supplier", "agent-reseller"}
    roles = get_roles(db)
    return {
        "status": "success",
        "data": [
            role
            for role in roles
            if role.is_active and role.slug in public_role_slugs
        ],
    }


@router.get("/")
def list_roles(
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-roles")),
):
    paginated = get_roles(
        db,
        page=params["page"],
        limit=params["limit"],
        search=params["search"],
    )
    return {"status": "success", "data": paginated["items"], **paginated}


@router.get("/{role_id}")
def detail_role(
    role_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-roles")),
):
    return {"status": "success", "data": get_role(db, role_id)}


@router.post("/")
def add_role(
    data: RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("create-roles")),
):
    return {
        "status": "success",
        "message": "Role created successfully",
        "data": create_role(db, data, actor=current_user, request=request),
    }


@router.put("/{role_id}")
def edit_role(
    role_id: int,
    data: RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-roles")),
):
    return {
        "status": "success",
        "message": "Role updated successfully",
        "data": update_role(db, role_id, data, actor=current_user, request=request),
    }


@router.delete("/{role_id}")
def remove_role(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("delete-roles")),
):
    delete_role(db, role_id, actor=current_user, request=request)
    return {"status": "success", "message": "Role deleted successfully"}


@router.post("/{role_id}/permissions")
def assign_permissions(
    role_id: int,
    data: AssignPermissions,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-roles")),
):
    permissions = assign_permissions_to_role(
        db,
        role_id,
        data.permission_ids,
        actor=current_user,
        request=request,
    )

    return {
        "status": "success",
        "message": "Permissions assigned successfully",
        "data": permissions,
    }


@router.get("/{role_id}/permissions")
def role_permissions(
    role_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-roles")),
):
    return {
        "status": "success",
        "data": get_role_permissions(db, role_id),
    }
