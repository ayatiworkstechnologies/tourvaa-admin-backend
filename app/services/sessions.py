from math import ceil
from uuid import uuid4
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.utils.money import utcnow
from app.models.sessions import UserSession
from app.models.users import User


def serialize_session(s: UserSession) -> dict:
    return {"id": s.id, "user_id": s.user_id, "session_id": s.session_id, "ip_address": s.ip_address, "user_agent": s.user_agent, "status": s.status, "revoked_at": s.revoked_at, "last_seen_at": s.last_seen_at, "created_at": s.created_at}


def create_session(db: Session, user: User, request: Request | None = None):
    s = UserSession(user_id=user.id, session_id=uuid4().hex, ip_address=request.client.host if request and request.client else None, user_agent=request.headers.get("user-agent") if request else None)
    db.add(s)
    db.flush()
    return s


def list_sessions(db: Session, page: int = 1, limit: int = 20, user_id: int | None = None):
    query = db.query(UserSession)
    if user_id:
        query = query.filter(UserSession.user_id == user_id)
    query = query.order_by(UserSession.id.desc())
    total = query.count()
    items = [serialize_session(session) for session in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def revoke_session(db: Session, session_id: int):
    s = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    s.status = "revoked"
    s.revoked_at = utcnow()
    db.commit()
    db.refresh(s)
    return serialize_session(s)


def force_logout_user(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.token_version = (user.token_version or 0) + 1
    db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.status == "active").update({"status": "revoked", "revoked_at": utcnow()})
    db.commit()
    return {"user_id": user_id, "revoked": True}


def list_login_history(db: Session, page: int = 1, limit: int = 20, user_id: int | None = None, status: str = ""):
    from app.models.sessions import LoginHistory
    query = db.query(LoginHistory)
    if user_id:
        query = query.filter(LoginHistory.user_id == user_id)
    if status:
        query = query.filter(LoginHistory.status == status)
    query = query.order_by(LoginHistory.id.desc())
    total = query.count()
    rows = query.offset((page - 1) * limit).limit(limit).all()
    items = [{"id": r.id, "user_id": r.user_id, "email": r.email, "status": r.status, "failure_reason": r.failure_reason, "client_type": r.client_type, "device_id": r.device_id, "device_name": r.device_name, "ip_address": r.ip_address, "user_agent": r.user_agent, "session_id": r.session_id, "created_at": r.created_at} for r in rows]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def expire_inactive_sessions(db: Session, older_than_days: int = 30):
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=older_than_days)
    count = db.query(UserSession).filter(UserSession.status == "active", UserSession.last_seen_at < cutoff).update({"status": "expired", "revoked_at": utcnow()})
    db.commit()
    return {"expired": count, "older_than_days": older_than_days}
