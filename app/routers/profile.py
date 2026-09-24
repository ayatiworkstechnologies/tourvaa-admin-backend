from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import require_any_permission
from app.schemas.profile import PasswordUpdate, ProfileUpdate
from app.models.users import User
from app.services.users import serialize_user
from app.services.auth import change_password_everywhere
from app.auth.security import verify_password

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/me")
def my_profile(current_user: User = Depends(require_any_permission("profile.view", "view-profile"))):
    return {"status": "success", "data": serialize_user(current_user)}


@router.put("/me")
def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(require_any_permission("profile.edit", "update-profile")),
    db: Session = Depends(get_db),
):
    current_user.name = data.name
    current_user.phone = data.phone
    current_user.profile_image = data.profile_image
    current_user.address = data.address
    current_user.country = data.country
    current_user.state = data.state
    current_user.city = data.city
    current_user.pincode = data.pincode
    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profile updated successfully",
        "data": serialize_user(current_user),
    }


@router.put("/password")
def update_password(
    data: PasswordUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_any_permission("profile.edit", "update-profile")),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password must be different from current password",
        )

    change_password_everywhere(db, current_user, data.new_password, request=request, background_tasks=background_tasks)

    return {
        "status": "success",
        "message": "Password updated successfully. Please sign in again on all devices.",
    }
