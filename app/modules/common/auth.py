from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User, UserRole


ACTION_TO_DOTTED = {
    "view": "view",
    "create": "create",
    "update": "edit",
    "delete": "delete",
}

DOTTED_TO_ACTION = {
    "view": "view",
    "create": "create",
    "edit": "update",
    "update": "update",
    "delete": "delete",
}

MODULE_ALIASES = {
    "email": "email_templates",
    "email_templates": "email",
}


def expand_permission_slugs(permission_slugs: tuple[str, ...]):
    expanded = set(permission_slugs)

    for slug in permission_slugs:
        if "." in slug:
            module, action = slug.split(".", 1)
            legacy_action = DOTTED_TO_ACTION.get(action)
            legacy_module = MODULE_ALIASES.get(module, module)

            if legacy_action:
                expanded.add(f"{legacy_action}-{legacy_module}")
            continue

        if "-" in slug:
            action, module = slug.split("-", 1)
            dotted_action = ACTION_TO_DOTTED.get(action)
            dotted_module = MODULE_ALIASES.get(module, module)

            if dotted_action:
                expanded.add(f"{dotted_module}.{dotted_action}")

    return list(expanded)


def get_user_role_ids(user: User):
    role_ids = {user.role_id} if user.role_id else set()
    role_ids.update(user_role.role_id for user_role in user.user_roles)
    return [role_id for role_id in role_ids if role_id]


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization token missing")

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    try:
        token = parts[1]
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("user_id")
        token_version = payload.get("token_version")
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid user")

        if token_version is None or token_version != user.token_version:
            raise HTTPException(status_code=401, detail="Token has expired")

        if user.approval_status != "approved" or not user.is_active:
            raise HTTPException(status_code=403, detail="User is not approved")

        if user.role and not user.role.is_active:
            raise HTTPException(status_code=403, detail="Role is inactive")

        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_permission(permission_slug: str):
    return require_any_permission(permission_slug)


def require_any_permission(*permission_slugs: str):
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(permission_slugs)

        if not role_ids:
            raise HTTPException(status_code=403, detail="Role is required")

        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.slug.in_(allowed_slugs))
            .filter(Permission.is_active == True)
            .first()
        )

        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")

        return current_user

    return dependency
