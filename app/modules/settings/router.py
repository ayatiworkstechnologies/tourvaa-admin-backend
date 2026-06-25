from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.cms.models import City, Country
from app.modules.cms.service import list_cities, list_countries
from app.modules.common.auth import require_permission
from app.modules.users.models import User
from app.modules.settings.schemas import (
    ApiSettingUpdate,
    ApiSettingsUpdate,
    PaymentSettingUpdate,
    PaymentSettingsUpdate,
    SettingsBulkUpdate,
    SystemSettingsUpdate,
)
from app.modules.settings.service import (
    get_api_settings_payload,
    get_api_settings,
    get_payment_settings,
    get_payment_settings_payload,
    get_settings,
    get_system_settings,
    mask_secret,
    update_api_settings_payload,
    update_api_setting,
    update_payment_settings_payload,
    update_payment_setting,
    update_system_settings,
    update_settings,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


# ── Dropdown helpers used by portal forms ──────────────────────────────────────

@router.get("/countries")
def settings_countries(
    search: str = Query(default=""),
    page: int = Query(default=1),
    limit: int = Query(default=300),
    db: Session = Depends(get_db),
):
    return {"status": "success", **list_countries(db, page, limit, search)}


@router.get("/cities")
def settings_cities(
    search: str = Query(default=""),
    country_id: str = Query(default=""),
    page: int = Query(default=1),
    limit: int = Query(default=500),
    db: Session = Depends(get_db),
):
    return {"status": "success", **list_cities(db, page, limit, search, country_id)}


@router.get("/public")
def public_settings(db: Session = Depends(get_db)):
    """Returns only is_public settings — safe to call without auth."""
    from app.modules.settings.models import AppSetting
    rows = db.query(AppSetting).filter(AppSetting.is_public == True).all()  # noqa: E712
    return {"data": {row.key: row.value for row in rows}}


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


@router.get("/system")
def system_settings(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {"status": "success", "data": get_system_settings(db)}


@router.put("/system")
def save_system_settings(
    data: SystemSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-settings")),
):
    return {
        "status": "success",
        "message": "System settings updated successfully",
        "data": update_system_settings(
            db,
            data.model_dump(exclude_unset=True),
            actor=current_user,
            request=request,
        ),
    }


@router.get("/payment")
def list_payment_settings(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {
        "status": "success",
        "data": [
            {
                "id": item.id,
                "provider_name": item.provider_name,
                "is_enabled": item.is_enabled,
                "public_key": item.public_key,
                "secret_key": mask_secret(item.secret_key),
                "surcharge_percentage": item.surcharge_percentage,
                "mode": item.mode,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in get_payment_settings(db)
        ],
    }


@router.put("/payment")
def save_payment_settings(
    data: PaymentSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-settings")),
):
    return {
        "status": "success",
        "message": "Payment settings updated successfully",
        "data": update_payment_settings_payload(
            db,
            data.model_dump(exclude_unset=True),
            actor=current_user,
            request=request,
        ),
    }


@router.get("/payment/summary")
def payment_settings_summary(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {"status": "success", "data": get_payment_settings_payload(db)}


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
    return {
        "status": "success",
        "data": [
            {
                "id": item.id,
                "api_name": item.api_name,
                "api_key": mask_secret(item.api_key),
                "api_secret": mask_secret(item.api_secret),
                "api_url": item.api_url,
                "is_enabled": item.is_enabled,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in get_api_settings(db)
        ],
    }


@router.put("/api")
def save_api_settings(
    data: ApiSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update-settings")),
):
    return {
        "status": "success",
        "message": "API settings updated successfully",
        "data": update_api_settings_payload(
            db,
            data.model_dump(exclude_unset=True),
            actor=current_user,
            request=request,
        ),
    }


@router.get("/api/summary")
def api_settings_summary(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-settings")),
):
    return {"status": "success", "data": get_api_settings_payload(db)}


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
