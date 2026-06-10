from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.schemas import RoleCreate, RoleUpdate


def get_roles(db: Session):
    return db.query(Role).order_by(Role.id.desc()).all()


def get_role(db: Session, role_id: int):
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    return role


def create_role(db: Session, data: RoleCreate):
    existing = db.query(Role).filter(Role.slug == data.slug).first()

    if existing:
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(name=data.name, slug=data.slug)

    db.add(role)
    db.commit()
    db.refresh(role)

    return role


def update_role(db: Session, role_id: int, data: RoleUpdate):
    role = get_role(db, role_id)

    if data.name is not None:
        role.name = data.name

    if data.slug is not None:
        role.slug = data.slug

    if data.is_active is not None:
        role.is_active = data.is_active

    db.commit()
    db.refresh(role)

    return role


def delete_role(db: Session, role_id: int):
    role = get_role(db, role_id)

    db.delete(role)
    db.commit()

    return True


def assign_permissions_to_role(db: Session, role_id: int, permission_ids: list[int]):
    role = get_role(db, role_id)

    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()

    for permission_id in permission_ids:
        permission = db.query(Permission).filter(Permission.id == permission_id).first()

        if permission:
            role_permission = RolePermission(
                role_id=role.id,
                permission_id=permission.id
            )
            db.add(role_permission)

    db.commit()

    return get_role_permissions(db, role_id)


def get_role_permissions(db: Session, role_id: int):
    role = get_role(db, role_id)

    permissions = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role.id)
        .all()
    )

    return permissions