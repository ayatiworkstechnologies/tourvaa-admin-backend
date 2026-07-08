from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.booking_calendar import service
from app.modules.common.auth import get_current_user, require_any_permission

router = APIRouter(tags=["Booking Calendar"])


@router.post("/bookings/{booking_id}/calendar-sync")
def sync_calendar(booking_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("bookings.view", "bookings.edit"))):
    result = service.sync_booking_to_calendar(db, booking_id=booking_id, actor=current_user)
    return {"status": "success", "message": "Calendar event synced", "data": result}


@router.get("/bookings/{booking_id}/calendar-event")
def get_calendar_event(booking_id: int, db: Session = Depends(get_db), current_user=Depends(require_any_permission("bookings.view"))):
    return {"status": "success", "data": service.get_calendar_event(db, booking_id=booking_id, actor=current_user)}


@router.get("/bookings/{booking_id}/calendar-event/download")
def download_ics(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_any_permission("bookings.view")),
):
    # returns the raw .ics file so it can be opened directly / added to a calendar app
    fs_path, filename = service.get_ics_path(db, booking_id=booking_id, actor=current_user)
    return FileResponse(path=fs_path, filename=filename, media_type="text/calendar")
