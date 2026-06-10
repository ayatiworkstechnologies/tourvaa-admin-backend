from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization token missing")

    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid user")

        if user.approval_status != "approved" or not user.is_active:
            raise HTTPException(status_code=403, detail="User is not approved")

        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_permission(permission_slug: str):
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if not current_user.role_id:
            raise HTTPException(status_code=403, detail="Role is required")

        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == current_user.role_id)
            .filter(Permission.slug == permission_slug)
            .filter(Permission.is_active == True)
            .first()
        )

        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")

        return current_user

    return dependency
