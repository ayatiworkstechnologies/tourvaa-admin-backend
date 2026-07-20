import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_storage_root
from app.models.booking_calendar import BookingCalendarEvent
from app.models.bookings import Booking
from app.utils.money import utcnow
from app.models.users import User


def _ics_content(booking: Booking, uid: str) -> str:
    """Generate iCalendar (.ics) file content for a booking."""
    start = booking.tour_start_date
    end = booking.tour_end_date or booking.tour_start_date

    def _fmt(dt):
        if not dt:
            return utcnow().strftime("%Y%m%dT%H%M%SZ")
        if hasattr(dt, "strftime"):
            return dt.strftime("%Y%m%dT%H%M%SZ")
        return str(dt).replace("-", "").replace(":", "").replace(" ", "T")

    tour_name = booking.tour.title if booking.tour else "Tour Booking"
    customer_name = booking.customer.user.name if booking.customer and booking.customer.user else "Customer"
    supplier_name = booking.supplier.supplier_name if booking.supplier else ""
    description = f"Booking: {booking.booking_code}\\nCustomer: {customer_name}\\nSupplier: {supplier_name}\\nTravellers: {booking.total_travellers or 0}"

    now_str = utcnow().strftime("%Y%m%dT%H%M%SZ")

    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Tourvaa//BookingCalendar//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_str}
DTSTART;VALUE=DATE:{_fmt(start)[:8]}
DTEND;VALUE=DATE:{_fmt(end)[:8]}
SUMMARY:{tour_name} - {booking.booking_code}
DESCRIPTION:{description}
LOCATION:{booking.tour.start_location if booking.tour else ""}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""


def _serialize(event: BookingCalendarEvent) -> dict:
    return {
        "id": event.id,
        "booking_id": event.booking_id,
        "booking_code": event.booking.booking_code if event.booking else None,
        "provider": event.provider,
        "external_event_id": event.external_event_id,
        "event_url": event.event_url,
        "ical_uid": event.ical_uid,
        "ics_file_path": event.ics_file_path,
        "sync_status": event.sync_status,
        "sync_error": event.sync_error,
        "retry_count": event.retry_count,
        "last_synced_at": event.last_synced_at,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }


def sync_booking_to_calendar(db: Session, booking_id: int, actor: Optional[User] = None) -> dict:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    existing = db.query(BookingCalendarEvent).filter(BookingCalendarEvent.booking_id == booking_id).first()

    uid = str(uuid.uuid4())
    if existing:
        uid = existing.ical_uid or uid

    # Generate .ics file
    ics_dir = get_storage_root().joinpath("calendars")
    ics_dir.mkdir(parents=True, exist_ok=True)
    ics_filename = f"{booking.booking_code or booking_id}.ics"
    ics_path = ics_dir / ics_filename

    try:
        ics_content = _ics_content(booking, uid)
        ics_path.write_text(ics_content, encoding="utf-8")
        ics_relative = f"/storage/calendars/{ics_filename}"
        sync_status = "synced"
        sync_error = None
    except Exception as exc:
        sync_status = "failed"
        sync_error = str(exc)
        ics_relative = None

    now = utcnow()

    if existing:
        existing.ical_uid = uid
        existing.ics_file_path = ics_relative or existing.ics_file_path
        existing.sync_status = sync_status
        existing.sync_error = sync_error
        existing.last_synced_at = now
        if sync_status == "failed":
            existing.retry_count = (existing.retry_count or 0) + 1
        else:
            existing.retry_count = 0
        db.commit()
        db.refresh(existing)
        return _serialize(existing)
    else:
        event = BookingCalendarEvent(
            booking_id=booking_id,
            provider="internal",
            ical_uid=uid,
            ics_file_path=ics_relative,
            sync_status=sync_status,
            sync_error=sync_error,
            last_synced_at=now,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return _serialize(event)


def get_calendar_event(db: Session, booking_id: int, actor: Optional[User] = None) -> dict:
    from app.services.bookings import _ensure_booking_access
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_booking_access(booking, actor)
    event = db.query(BookingCalendarEvent).filter(BookingCalendarEvent.booking_id == booking_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="No calendar event found for this booking")
    return _serialize(event)


def get_ics_path(db: Session, booking_id: int, actor: Optional[User] = None) -> tuple[str, str]:
    """Returns (filesystem_path, filename) for FileResponse."""
    from app.services.bookings import _ensure_booking_access
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_booking_access(booking, actor)
    event = db.query(BookingCalendarEvent).filter(BookingCalendarEvent.booking_id == booking_id).first()
    if not event or not event.ics_file_path:
        raise HTTPException(status_code=404, detail="Calendar file not found - please sync first")
    fs_path = str(get_storage_root()) + event.ics_file_path.replace("/storage", "")
    import os
    if not os.path.exists(fs_path):
        raise HTTPException(status_code=404, detail="Calendar file missing - please re-sync")
    booking_code = event.booking.booking_code if event.booking else str(booking_id)
    return fs_path, f"{booking_code}.ics"
