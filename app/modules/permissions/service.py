from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.permissions.models import Permission
from app.modules.permissions.schemas import PermissionCreate, PermissionUpdate


PERMISSION_ACTIONS = ["get", "post", "put", "delete"]


def get_permissions(db: Session):
    return db.query(Permission).order_by(Permission.id.desc()).all()


def get_permission(db: Session, permission_id: int):
    permission = db.query(Permission).filter(Permission.id == permission_id).first()

    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    return permission


def create_permission(db: Session, data: PermissionCreate):
    existing = db.query(Permission).filter(Permission.slug == data.slug).first()

    if existing:
        raise HTTPException(status_code=400, detail="Permission already exists")

    if data.action not in PERMISSION_ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid permission action")

    permission = Permission(
        name=data.name,
        slug=data.slug,
        module=data.module,
        action=data.action,
    )

    db.add(permission)
    db.commit()
    db.refresh(permission)

    return permission


def update_permission(db: Session, permission_id: int, data: PermissionUpdate):
    permission = get_permission(db, permission_id)

    if data.name is not None:
        permission.name = data.name

    if data.slug is not None:
        permission.slug = data.slug

    if data.module is not None:
        permission.module = data.module

    if data.action is not None:
        if data.action not in PERMISSION_ACTIONS:
            raise HTTPException(status_code=400, detail="Invalid permission action")

        permission.action = data.action

    if data.is_active is not None:
        permission.is_active = data.is_active

    db.commit()
    db.refresh(permission)

    return permission


def delete_permission(db: Session, permission_id: int):
    permission = get_permission(db, permission_id)

    db.delete(permission)
    db.commit()

    return True
