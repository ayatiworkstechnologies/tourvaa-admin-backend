from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_permission
from app.modules.users.models import User
from app.modules.settings.schemas import ApiSettingUpdate, PaymentSettingUpdate, SettingsBulkUpdate
from app.modules.settings.service import (
    get_api_settings,
    get_payment_settings,
    get_settings,
    update_api_setting,
    update_payment_setting,
    update_settings,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/")
def list_settings(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {"status": "success", "data": get_settings(db)}


@router.put("/")
def save_settings(
    data: SettingsBulkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-settings")),
):
    return {
        "status": "success",
        "message": "Settings updated successfully",
        "data": update_settings(db, data.settings, actor=current_user, request=request),
    }


@router.get("/payment")
def list_payment_settings(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {"status": "success", "data": get_payment_settings(db)}


@router.put("/payment/{provider_name}")
def save_payment_setting(
    provider_name: str,
    data: PaymentSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-settings")),
):
    setting = update_payment_setting(
        db,
        provider_name,
        data.model_dump(exclude_unset=True),
        actor=current_user,
        request=request,
    )

    if not setting:
        raise HTTPException(status_code=404, detail="Payment provider not found")

    return {"status": "success", "message": "Payment setting updated", "data": setting}


@router.get("/api")
def list_api_settings(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {"status": "success", "data": get_api_settings(db)}


@router.put("/api/{api_name}")
def save_api_setting(
    api_name: str,
    data: ApiSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-settings")),
):
    setting = update_api_setting(
        db,
        api_name,
        data.model_dump(exclude_unset=True),
        actor=current_user,
        request=request,
    )

    if not setting:
        raise HTTPException(status_code=404, detail="API setting not found")

    return {"status": "success", "message": "API setting updated", "data": setting}
