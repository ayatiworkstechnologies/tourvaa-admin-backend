from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_permission
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
    roles = get_roles(db)
    return {
        "status": "success",
        "data": [role for role in roles if role.is_active],
    }


@router.get("/")
def list_roles(db: Session = Depends(get_db), _=Depends(require_permission("view-roles"))):
    return {"status": "success", "data": get_roles(db)}


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
    db: Session = Depends(get_db),
    _=Depends(require_permission("create-roles")),
):
    return {
        "status": "success",
        "message": "Role created successfully",
        "data": create_role(db, data),
    }


@router.put("/{role_id}")
def edit_role(
    role_id: int,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-roles")),
):
    return {
        "status": "success",
        "message": "Role updated successfully",
        "data": update_role(db, role_id, data),
    }


@router.delete("/{role_id}")
def remove_role(
    role_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("delete-roles")),
):
    delete_role(db, role_id)
    return {"status": "success", "message": "Role deleted successfully"}


@router.post("/{role_id}/permissions")
def assign_permissions(
    role_id: int,
    data: AssignPermissions,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-roles")),
):
    permissions = assign_permissions_to_role(db, role_id, data.permission_ids)

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
