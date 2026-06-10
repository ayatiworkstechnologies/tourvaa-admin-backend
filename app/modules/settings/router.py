from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_permission
from app.modules.settings.schemas import SettingsBulkUpdate
from app.modules.settings.service import get_settings, update_settings

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
    db: Session = Depends(get_db),
    _=Depends(require_permission("update-settings")),
):
    return {
        "status": "success",
        "message": "Settings updated successfully",
        "data": update_settings(db, data.settings),
    }
