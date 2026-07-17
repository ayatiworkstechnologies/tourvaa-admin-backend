import secrets
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.checkout import CheckoutSession
from app.schemas.checkout import CheckoutConfirm, CheckoutStart, CheckoutUpdate
from app.utils.money import utcnow
from app.models.users import User

SESSION_TTL_HOURS = 24


def _key() -> str:
    return secrets.token_urlsafe(40)


def _ensure_session_owner(s: CheckoutSession, current_user: Optional[User]) -> None:
    """Once a checkout session is claimed by a user, only that same user may view/mutate/confirm it."""
    if s.user_id and (not current_user or current_user.id != s.user_id):
        raise HTTPException(status_code=403, detail="Checkout session access denied")


def _ensure_session_not_expired(s: CheckoutSession) -> None:
    """Reject an expired session before it can be resumed or mutated."""
    if s.expires_at and s.expires_at <= utcnow():
        raise HTTPException(status_code=410, detail="Checkout session has expired")


def _serialize(s: CheckoutSession) -> dict:
    return {
        "id": s.id,
        "session_key": s.session_key,
        "user_id": s.user_id,
        "customer_id": s.customer_id,
        "tour_id": s.tour_id,
        "tour_calendar_id": s.tour_calendar_id,
        "step": s.step,
        "status": s.status,
        "data": s.data,
        "booking_id": s.booking_id,
        "expires_at": s.expires_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def start_session(db: Session, body: CheckoutStart, current_user: Optional[User]) -> dict:
    # If a session_key was provided (guest resumed after login), reuse that session
    if body.session_key:
        existing = db.query(CheckoutSession).filter(CheckoutSession.session_key == body.session_key).first()
        if existing and existing.status == "active":
            _ensure_session_not_expired(existing)
            _ensure_session_owner(existing, current_user)
            if current_user and not existing.user_id:
                existing.user_id = current_user.id
                from app.models.customers import Customer
                customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
                if customer:
                    existing.customer_id = customer.id
            db.commit()
            db.refresh(existing)
            return _serialize(existing)

    session = CheckoutSession(
        session_key=_key(),
        tour_id=body.tour_id,
        tour_calendar_id=body.tour_calendar_id,
        step="travellers",
        status="active",
        data={},
        expires_at=utcnow() + timedelta(hours=SESSION_TTL_HOURS),
    )
    if current_user:
        session.user_id = current_user.id
        from app.models.customers import Customer
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if customer:
            session.customer_id = customer.id

    db.add(session)
    db.commit()
    db.refresh(session)
    return _serialize(session)


def get_session(db: Session, session_key: str, current_user: Optional[User]) -> dict:
    s = db.query(CheckoutSession).filter(CheckoutSession.session_key == session_key).first()
    if not s:
        raise HTTPException(status_code=404, detail="Checkout session not found")
    if s.status == "abandoned":
        raise HTTPException(status_code=410, detail="Checkout session has been abandoned")
    _ensure_session_not_expired(s)
    _ensure_session_owner(s, current_user)
    # Attach user to session if they just logged in
    if current_user and not s.user_id:
        s.user_id = current_user.id
        from app.models.customers import Customer
        customer = db.query(Customer).filter(Customer.user_id == current_user.id).first()
        if customer:
            s.customer_id = customer.id
        db.commit()
        db.refresh(s)
    return _serialize(s)


def update_session(db: Session, session_key: str, body: CheckoutUpdate, current_user: Optional[User]) -> dict:
    s = db.query(CheckoutSession).filter(CheckoutSession.session_key == session_key).first()
    if not s or s.status != "active":
        raise HTTPException(status_code=404, detail="Active checkout session not found")
    _ensure_session_not_expired(s)
    _ensure_session_owner(s, current_user)

    if body.step:
        s.step = body.step
    if body.data is not None:
        existing = s.data or {}
        existing.update(body.data)
        s.data = existing
    if current_user and not s.user_id:
        s.user_id = current_user.id

    db.commit()
    db.refresh(s)
    return _serialize(s)


def confirm_session(db: Session, session_key: str, body: CheckoutConfirm, current_user: User) -> dict:
    s = db.query(CheckoutSession).filter(CheckoutSession.session_key == session_key).first()
    if not s or s.status != "active":
        raise HTTPException(status_code=404, detail="Active checkout session not found")
    _ensure_session_not_expired(s)
    _ensure_session_owner(s, current_user)
    if not s.tour_id:
        raise HTTPException(status_code=400, detail="No tour selected in this checkout session")
    if not s.customer_id:
        raise HTTPException(status_code=400, detail="Customer identity not resolved — please log in first")

    from app.services.bookings import create_booking
    from app.schemas.bookings import BookingAddonPayload, BookingCreate, BookingTravellerPayload

    payload = s.data or {}
    travellers_raw = payload.get("travellers", [])
    travellers = [BookingTravellerPayload(**t) for t in travellers_raw]

    def _addons(raw_list):
        return [BookingAddonPayload(**a) if isinstance(a, dict) else BookingAddonPayload(id=int(a)) for a in (raw_list or [])]

    booking_data = BookingCreate(
        tour_id=s.tour_id,
        tour_calendar_id=s.tour_calendar_id,
        customer_id=s.customer_id,
        travellers=travellers,
        optional_activities=_addons(payload.get("optional_activities", [])),
        accommodations=_addons(payload.get("accommodations", [])),
        extensions=_addons(payload.get("extensions", [])),
        notes=body.notes or payload.get("notes"),
        promo_code=body.promo_code or payload.get("promo_code"),
        booking_source="customer",
    )

    booking = create_booking(db, booking_data, actor=current_user)
    s.booking_id = booking["id"]
    s.status = "completed"
    s.step = "payment"
    db.commit()
    db.refresh(s)

    return {"session": _serialize(s), "booking": booking}
