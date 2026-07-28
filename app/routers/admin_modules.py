from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.admin_modules import get_admin_modules, list_all_admin_modules, set_admin_module_active
from app.auth.permissions import require_permission

router = APIRouter(prefix="/modules", tags=["Admin Modules"])


class AdminModuleStatusUpdate(BaseModel):
    is_active: bool


def _serialize(module):
    return {
        "id": module.id,
        "name": module.name,
        "slug": module.slug,
        "description": module.description,
        "is_active": module.is_active,
        "is_system": module.is_system,
    }


@router.get("")
@router.get("/")
def list_admin_modules(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-permissions")),
):
    return {"status": "success", "data": get_admin_modules(db)}


@router.get("/all")
def list_all_modules(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-permissions")),
):
    return {"status": "success", "data": [_serialize(m) for m in list_all_admin_modules(db)]}


@router.patch("/{module_id}")
def update_module_status(
    module_id: int,
    data: AdminModuleStatusUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-permissions")),
):
    module = set_admin_module_active(db, module_id, data.is_active)
    return {"status": "success", "message": "Module updated", "data": _serialize(module)}
