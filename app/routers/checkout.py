from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import checkout as service
from app.schemas.checkout import CheckoutConfirm, CheckoutStart, CheckoutUpdate
from app.auth.permissions import get_current_user

router = APIRouter(prefix="/checkout", tags=["Checkout"])


def _optional_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Returns the current user or None for guest callers."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization=authorization, db=db)
    except Exception:
        return None


@router.post("/start")
def start_checkout(body: CheckoutStart, db: Session = Depends(get_db), current_user=Depends(_optional_user)):
    result = service.start_session(db, body=body, current_user=current_user)
    return {"status": "success", "message": "Checkout session started", "data": result}


@router.get("/session/{session_key}")
def get_checkout_session(session_key: str, db: Session = Depends(get_db), current_user=Depends(_optional_user)):
    result = service.get_session(db, session_key=session_key, current_user=current_user)
    return {"status": "success", "data": result}


@router.patch("/session/{session_key}")
def update_checkout_session(session_key: str, body: CheckoutUpdate, db: Session = Depends(get_db), current_user=Depends(_optional_user)):
    result = service.update_session(db, session_key=session_key, body=body, current_user=current_user)
    return {"status": "success", "message": "Session updated", "data": result}


@router.post("/session/{session_key}/confirm")
def confirm_checkout(
    session_key: str,
    body: CheckoutConfirm,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = service.confirm_session(db, session_key=session_key, body=body, current_user=current_user)
    return {"status": "success", "message": "Booking created from checkout session", "data": result}
