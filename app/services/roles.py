from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.roles import Role
from app.models.permissions import Permission, RolePermission
from app.schemas.roles import RoleCreate, RoleUpdate
from app.services.audit import log_audit
from app.models.users import User


def serialize_role(role: Role):
    return {
        "id": role.id,
        "name": role.name,
        "slug": role.slug,
        "is_active": role.is_active,
        "is_system": role.is_system,
        "created_at": role.created_at,
    }


def get_roles(db: Session, page: int | None = None, limit: int | None = None, search: str = ""):
    query = db.query(Role)

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(or_(Role.name.ilike(pattern), Role.slug.ilike(pattern)))

    query = query.order_by(Role.id.desc())

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


def get_role(db: Session, role_id: int):
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    return role


def create_role(
    db: Session,
    data: RoleCreate,
    actor: User | None = None,
    request: Request | None = None,
):
    existing = db.query(Role).filter(Role.slug == data.slug).first()

    if existing:
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(name=data.name.strip(), slug=data.slug.strip().lower())

    db.add(role)
    db.flush()
    log_audit(
        db,
        actor=actor,
        action="create_role",
        entity_type="role",
        entity_id=role.id,
        new_values=serialize_role(role),
        request=request,
    )
    db.commit()
    db.refresh(role)

    return role


def update_role(
    db: Session,
    role_id: int,
    data: RoleUpdate,
    actor: User | None = None,
    request: Request | None = None,
):
    role = get_role(db, role_id)
    old_values = serialize_role(role)

    if role.is_system and data.slug is not None and data.slug != role.slug:
        raise HTTPException(status_code=400, detail="System role slug cannot be changed")

    if data.name is not None:
        role.name = data.name.strip()

    if data.slug is not None:
        existing = db.query(Role).filter(Role.slug == data.slug, Role.id != role_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Role already exists")

        role.slug = data.slug.strip().lower()

    if data.is_active is not None:
        if role.is_system and data.is_active is False:
            raise HTTPException(status_code=400, detail="System role cannot be disabled")

        role.is_active = data.is_active

    log_audit(
        db,
        actor=actor,
        action="update_role",
        entity_type="role",
        entity_id=role.id,
        old_values=old_values,
        new_values=serialize_role(role),
        request=request,
    )
    db.commit()
    db.refresh(role)

    return role


def delete_role(
    db: Session,
    role_id: int,
    actor: User | None = None,
    request: Request | None = None,
):
    role = get_role(db, role_id)

    if role.is_system:
        raise HTTPException(status_code=400, detail="System role cannot be deleted")

    if role.users:
        raise HTTPException(status_code=400, detail="Role is assigned to users")

    old_values = serialize_role(role)
    db.delete(role)
    log_audit(
        db,
        actor=actor,
        action="delete_role",
        entity_type="role",
        entity_id=role_id,
        old_values=old_values,
        request=request,
    )
    db.commit()

    return True


def assign_permissions_to_role(
    db: Session,
    role_id: int,
    permission_ids: list[int],
    actor: User | None = None,
    request: Request | None = None,
):
    role = get_role(db, role_id)
    unique_permission_ids = sorted(set(permission_ids))
    found_permissions = (
        db.query(Permission)
        .filter(Permission.id.in_(unique_permission_ids))
        .all()
        if unique_permission_ids
        else []
    )
    found_ids = {permission.id for permission in found_permissions}
    invalid_ids = [permission_id for permission_id in unique_permission_ids if permission_id not in found_ids]

    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid permission IDs",
                "invalid_ids": invalid_ids,
            },
        )

    old_permissions = [permission.slug for permission in get_role_permissions(db, role_id)]

    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()

    for permission in found_permissions:
        role_permission = RolePermission(
            role_id=role.id,
            permission_id=permission.id
        )
        db.add(role_permission)

    log_audit(
        db,
        actor=actor,
        action="assign_permissions",
        entity_type="role",
        entity_id=role.id,
        old_values={"permissions": old_permissions},
        new_values={"permission_ids": unique_permission_ids},
        request=request,
    )
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
