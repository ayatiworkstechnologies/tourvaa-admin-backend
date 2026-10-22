from html import escape

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.booking_modifications import BookingModificationRequest
from app.models.users import User
from app.schemas.bookings import BookingModificationCreate, BookingModificationDecision, BookingTravelDateUpdate, BookingUpdate
from app.services.audit import log_audit
from app.services.notification_delivery import dispatch_admin_lifecycle_emails, dispatch_lifecycle_email
from app.utils.money import utcnow


def _role(user: User) -> str:
    return str(getattr(user, "user_type", "user") or "user").lower()


def _serialize(row: BookingModificationRequest) -> dict:
    return {
        "id": row.id, "booking_id": row.booking_id, "status": row.status,
        "requester_user_id": row.requester_user_id, "requester_type": row.requester_type,
        "proposed_changes": row.proposed_changes, "original_values": row.original_values,
        "reason": row.reason, "reviewed_by": row.reviewed_by,
        "decision_reason": row.decision_reason, "decision_history": row.decision_history or [],
        "reviewed_at": row.reviewed_at, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _change_summary(changes: dict) -> str:
    return ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in changes.items())


def _decision_recipient(row: BookingModificationRequest):
    booking = row.booking
    if row.requester_type == "agent" and booking.agent and booking.agent.user:
        return "agent", booking.agent.user.email, booking.agent.agent_name, f"{settings.FRONTEND_URL}/agent/bookings/{booking.id}"
    if row.requester_type == "supplier" and booking.supplier and booking.supplier.user:
        return "supplier", booking.supplier.user.email, booking.supplier.supplier_name, f"{settings.FRONTEND_URL}/supplier/bookings/{booking.id}"
    if row.requester_type == "customer" and booking.customer:
        return "customer", booking.customer.email, booking.customer.full_name, f"{settings.FRONTEND_URL}/customer/bookings/{booking.id}"
    return None


def create_modification_request(db: Session, booking_id: int, data: BookingModificationCreate, actor: User, request=None) -> dict:
    from app.services.bookings import get_booking_by_id, _ensure_booking_access

    booking = get_booking_by_id(db, booking_id, for_update=True)
    _ensure_booking_access(booking, actor)
    role = _role(actor)
    if role not in {"customer", "agent", "supplier"}:
        raise HTTPException(status_code=403, detail="Only a booking customer, agent, or assigned supplier can request a modification")
    changes = data.proposed_changes.model_dump(exclude_unset=True, mode="json")
    if not changes:
        raise HTTPException(status_code=422, detail="At least one proposed change is required")
    if "tour_date" in changes and len(changes) != 1:
        raise HTTPException(status_code=422, detail="A travel-date change must be requested separately so availability can be applied atomically")
    existing = db.query(BookingModificationRequest.id).filter(
        BookingModificationRequest.booking_id == booking.id,
        BookingModificationRequest.status == "pending",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This booking already has a pending modification request")
    original = {key: getattr(booking, key, None) for key in changes}
    row = BookingModificationRequest(
        booking_id=booking.id, requester_user_id=actor.id, requester_type=role,
        proposed_changes=changes, original_values=original, reason=data.reason,
        decision_history=[{"status": "pending", "actor_id": actor.id, "at": utcnow().isoformat(), "reason": data.reason}],
    )
    db.add(row)
    db.flush()
    detail = _change_summary(changes)
    admin_url = f"{settings.FRONTEND_URL}/admin/bookings/{booking.id}"
    dispatch_admin_lifecycle_emails(
        db, event="booking_modification_requested", entity_type="booking_modification_request", entity_id=row.id,
        template_key="booking_modification_requested",
        values={"booking_code": booking.booking_code, "tour_name": booking.tour_name, "detail": detail, "login_url": admin_url},
        fallback_subject=f"Booking change requested - {booking.booking_code}",
        fallback_html=f"<p>A {escape(role)} requested changes to booking {escape(booking.booking_code)}: {escape(detail)}</p>",
    )
    if booking.supplier and booking.supplier.user and booking.supplier.user.email and role != "supplier":
        supplier_url = f"{settings.FRONTEND_URL}/supplier/bookings/{booking.id}"
        dispatch_lifecycle_email(
            db, event="booking_modification_requested", entity_type="booking_modification_request", entity_id=row.id,
            recipient_type="supplier", recipient_email=booking.supplier.user.email, template_key="booking_modification_requested",
            values={"booking_code": booking.booking_code, "tour_name": booking.tour_name, "detail": detail, "login_url": supplier_url},
            fallback_subject=f"Booking change requested - {booking.booking_code}",
            fallback_html=f"<p>A change was requested for booking {escape(booking.booking_code)}. Review it in your portal.</p>",
        )
    log_audit(db, actor=actor, action="request_booking_modification", entity_type="booking_modification_request", entity_id=row.id, new_values=changes, request=request)
    db.commit(); db.refresh(row)
    return _serialize(row)


def list_modification_requests(db: Session, booking_id: int, actor: User) -> list[dict]:
    from app.services.bookings import get_booking_by_id, _ensure_booking_access
    booking = get_booking_by_id(db, booking_id)
    _ensure_booking_access(booking, actor)
    return [_serialize(row) for row in db.query(BookingModificationRequest).filter(BookingModificationRequest.booking_id == booking_id).order_by(BookingModificationRequest.id.desc()).all()]


def decide_modification_request(db: Session, booking_id: int, request_id: int, approve: bool, data: BookingModificationDecision, actor: User, request=None) -> dict:
    from app.services.bookings import update_booking, update_booking_travel_date

    row = db.query(BookingModificationRequest).filter(BookingModificationRequest.id == request_id, BookingModificationRequest.booking_id == booking_id).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Booking modification request not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Booking modification request has already been decided")
    row.status = "approved" if approve else "rejected"
    row.reviewed_by = actor.id
    row.reviewed_at = utcnow()
    row.decision_reason = data.reason
    history = list(row.decision_history or [])
    history.append({"status": row.status, "actor_id": actor.id, "at": row.reviewed_at.isoformat(), "reason": data.reason})
    row.decision_history = history
    if approve:
        changes = row.proposed_changes or {}
        if set(changes) == {"tour_date"}:
            update_booking_travel_date(db, row.booking_id, BookingTravelDateUpdate(tour_date=changes["tour_date"], reason=data.reason or row.reason), actor, request)
        else:
            update_booking(db, row.booking_id, BookingUpdate.model_validate(changes), actor, request)
    else:
        db.commit(); db.refresh(row)

    recipient = _decision_recipient(row)
    if recipient and recipient[1]:
        recipient_type, email, name, login_url = recipient
        template_key = "booking_modification_confirmed" if approve else "booking_modification_rejected"
        detail = _change_summary(row.proposed_changes or {})
        values = {"name": name, "booking_code": row.booking.booking_code, "tour_name": row.booking.tour_name,
                  "detail": detail, "reason": data.reason or "", "login_url": login_url,
                  "button_text": "View booking", "button_url": login_url}
        dispatch_lifecycle_email(
            db, event=template_key, entity_type="booking_modification_request", entity_id=row.id,
            recipient_type=recipient_type, recipient_email=email, template_key=template_key, values=values,
            fallback_subject=f"Booking change {'confirmed' if approve else 'not approved'} - {row.booking.booking_code}",
            fallback_html=f"<p>Your requested booking change was {'confirmed' if approve else 'not approved'}.</p><p>{escape(data.reason or detail)}</p>",
        )
    log_audit(db, actor=actor, action="approve_booking_modification" if approve else "reject_booking_modification", entity_type="booking_modification_request", entity_id=row.id, new_values={"status": row.status, "reason": data.reason}, request=request)
    db.commit(); db.refresh(row)
    return _serialize(row)
