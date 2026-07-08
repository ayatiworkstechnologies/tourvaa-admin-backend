from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.admin_modules import get_admin_modules
from app.auth.permissions import require_permission

router = APIRouter(prefix="/modules", tags=["Admin Modules"])


@router.get("")
@router.get("/")
def list_admin_modules(
    db: Session = Depends(get_db),
    _=Depends(require_permission("view-permissions")),
):
    return {"status": "success", "data": get_admin_modules(db)}
