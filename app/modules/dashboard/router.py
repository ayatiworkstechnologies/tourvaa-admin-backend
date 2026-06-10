from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.database import get_db
from app.config import settings
from app.modules.users.models import User
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_current_user_from_token(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization token missing")

    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        user_id = payload.get("user_id")

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid user")

        return user

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_dashboard_menus(permissions):
    menu_map = {
        "view-dashboard": "Dashboard",
        "view-users": "Users",
        "view-roles": "Roles",
        "view-permissions": "Permissions",
        "view-suppliers": "Suppliers",
        "view-agents": "Agents",
        "view-resellers": "Resellers",
        "view-customers": "Customers",
        "view-tours": "Tours",
        "view-bookings": "Bookings",
        "view-payments": "Payments",
        "view-reports": "Reports",
        "view-email": "Email Templates",
        "view-settings": "Settings",
        "view-profile": "Profile",
    }

    menus = []

    for permission in permissions:
        if permission.slug in menu_map:
            menus.append({
                "label": menu_map[permission.slug],
                "permission": permission.slug,
                "module": permission.module,
            })

    return menus


@router.get("/me")
def my_dashboard(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_db)
):
    permissions = (
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == current_user.role_id)
        .filter(Permission.is_active == True)
        .all()
    )

    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    pending_users = db.query(User).filter(User.approval_status == "pending").count()
    total_roles = db.query(Role).filter(Role.is_active == True).count()
    permission_slugs = {permission.slug for permission in permissions}

    can_view_users = "view-users" in permission_slugs
    can_manage_users = can_view_users or "update-users" in permission_slugs
    can_view_roles = "view-roles" in permission_slugs
    pending_approval_users = []

    if can_manage_users:
        pending_approval_users = (
            db.query(User)
            .filter(User.approval_status == "pending")
            .order_by(User.id.desc())
            .limit(5)
            .all()
        )

    return {
        "status": "success",
        "data": {
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "profile_image": current_user.profile_image,
                "role": {
                    "id": current_user.role.id if current_user.role else None,
                    "name": current_user.role.name if current_user.role else None,
                    "slug": current_user.role.slug if current_user.role else None,
                }
            },
            "permissions": [
                {
                    "name": permission.name,
                    "slug": permission.slug,
                    "module": permission.module,
                    "action": permission.action,
                }
                for permission in permissions
            ],
            "menus": get_dashboard_menus(permissions),
            "stats": {
                "users": total_users if can_view_users else 0,
                "active_users": active_users if can_view_users else 0,
                "roles": total_roles if can_view_roles else 0,
                "permissions": len(permissions),
                "pending_users": pending_users if can_manage_users else 0,
            },
            "pending_approvals": [
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role_id": user.role_id,
                    "role_name": user.role.name if user.role else None,
                    "created_at": user.created_at,
                }
                for user in pending_approval_users
            ],
        }
    }
