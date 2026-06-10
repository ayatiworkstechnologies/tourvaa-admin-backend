from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_permission
from app.modules.permissions.schemas import PermissionCreate, PermissionUpdate
from app.modules.permissions.service import (
    get_permissions,
    get_permission,
    create_permission,
    update_permission,
    delete_permission,
)

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get("/")
def list_permissions(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-permissions")),
):
    return {"status": "success", "data": get_permissions(db)}


@router.get("/{permission_id}")
def detail_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-permissions")),
):
    return {"status": "success", "data": get_permission(db, permission_id)}


@router.post("/")
def add_permission(
    data: PermissionCreate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("create-permissions")),
):
    return {
        "status": "success",
        "message": "Permission created successfully",
        "data": create_permission(db, data),
    }


@router.put("/{permission_id}")
def edit_permission(
    permission_id: int,
    data: PermissionUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-permissions")),
):
    return {
        "status": "success",
        "message": "Permission updated successfully",
        "data": update_permission(db, permission_id, data),
    }


@router.delete("/{permission_id}")
def remove_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("delete-permissions")),
):
    delete_permission(db, permission_id)
    return {"status": "success", "message": "Permission deleted successfully"}
