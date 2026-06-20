from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params
from app.modules.sessions.service import expire_inactive_sessions, force_logout_user, list_login_history, list_sessions, revoke_session

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("")
@router.get("/")
def sessions(params: dict = Depends(pagination_params), user_id: int = Query(default=0), db: Session = Depends(get_db), _=Depends(require_any_permission("sessions.view"))):
    return {"status": "success", **list_sessions(db, params["page"], params["limit"], user_id or None)}


@router.get("/login-history")
def login_history(params: dict = Depends(pagination_params), user_id: int = Query(default=0), status: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("sessions.view"))):
    return {"status": "success", **list_login_history(db, params["page"], params["limit"], user_id or None, status)}

@router.post("/expire-inactive")
def expire_inactive(days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), _=Depends(require_any_permission("sessions.revoke"))):
    return {"status": "success", "data": expire_inactive_sessions(db, days)}

@router.post("/{session_id}/revoke")
def revoke(session_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("sessions.revoke"))):
    return {"status": "success", "data": revoke_session(db, session_id)}

@router.post("/users/{user_id}/force-logout")
def force_logout(user_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("sessions.force_logout"))):
    return {"status": "success", "data": force_logout_user(db, user_id)}
