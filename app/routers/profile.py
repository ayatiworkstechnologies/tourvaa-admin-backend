from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import get_current_user
from app.schemas.profile import PasswordUpdate, ProfileUpdate
from app.models.users import User
from app.services.users import serialize_user
from app.auth.security import hash_password, verify_password

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/me")
def my_profile(current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": serialize_user(current_user)}


@router.put("/me")
def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password must be different from current password",
        )

    current_user.password = hash_password(data.new_password)
    current_user.token_version += 1
    db.commit()

    return {"status": "success", "message": "Password updated successfully"}
