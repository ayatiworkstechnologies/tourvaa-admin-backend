from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.permissions.models import Permission
from app.modules.permissions.schemas import PermissionCreate, PermissionUpdate


PERMISSION_ACTIONS = ["get", "post", "put", "delete"]


def get_permissions(db: Session, page: int | None = None, limit: int | None = None, search: str = ""):
    query = db.query(Permission)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                Permission.name.ilike(pattern),
                Permission.slug.ilike(pattern),
                Permission.module.ilike(pattern),
            )
        )

    query = query.order_by(Permission.id.desc())

    if page is None or limit is None:
        return query.all()

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


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
        name=data.name.strip(),
        slug=data.slug.strip().lower(),
        module=data.module.strip().lower(),
        action=data.action.strip().lower(),
    )

    db.add(permission)
    db.commit()
    db.refresh(permission)

    return permission


def update_permission(db: Session, permission_id: int, data: PermissionUpdate):
    permission = get_permission(db, permission_id)

    if data.name is not None:
        permission.name = data.name.strip()

    if data.slug is not None:
        if permission.is_system and data.slug != permission.slug:
            raise HTTPException(status_code=400, detail="System permission slug cannot be changed")

        existing = (
            db.query(Permission)
            .filter(Permission.slug == data.slug, Permission.id != permission_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Permission already exists")

        permission.slug = data.slug.strip().lower()

    if data.module is not None:
        permission.module = data.module.strip().lower()

    if data.action is not None:
        if data.action not in PERMISSION_ACTIONS:
            raise HTTPException(status_code=400, detail="Invalid permission action")

        permission.action = data.action.strip().lower()

    if data.is_active is not None:
        if permission.is_system and data.is_active is False:
            raise HTTPException(status_code=400, detail="System permission cannot be disabled")

        permission.is_active = data.is_active

    db.commit()
    db.refresh(permission)

    return permission


def delete_permission(db: Session, permission_id: int):
    permission = get_permission(db, permission_id)

    if permission.is_system:
        raise HTTPException(status_code=400, detail="System permission cannot be deleted")

    db.delete(permission)
    db.commit()

    return True
