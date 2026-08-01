import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_private_docs_root
from app.models.bookings import Booking
from app.models.tours import TourItinerary
from app.models.users import User
from app.utils.itinerary_pdf import generate_pdf


def _ensure_booking_owner(booking: Booking, actor: User) -> None:
    if not booking.customer or booking.customer.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Booking access denied")


def download_itinerary_pdf(db: Session, booking_id: int, actor: User) -> tuple[str, str]:
    """Returns (file_system_path, filename) for FileResponse. Generates the
    PDF on first request and caches it on disk, same pattern as invoices."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _ensure_booking_owner(booking, actor)
    if not booking.tour_id:
        raise HTTPException(status_code=404, detail="This booking has no associated tour itinerary")

    days = (
        db.query(TourItinerary)
        .filter(TourItinerary.tour_id == booking.tour_id)
        .order_by(TourItinerary.day_number.asc())
        .all()
    )
    if not days:
        raise HTTPException(status_code=404, detail="No itinerary is available for this tour yet")

    storage = get_private_docs_root().joinpath("itineraries")
    storage.mkdir(parents=True, exist_ok=True)
    filename = f"{booking.booking_code or booking.id}-itinerary.pdf"
    pdf_path = storage.joinpath(filename)

    if not pdf_path.exists():
        itinerary_data = {
            "booking_code": booking.booking_code or str(booking.id),
            "tour_name": booking.tour_name or "Tour",
            "customer_name": booking.customer.full_name if booking.customer else "",
            "tour_date": booking.tour_date or "",
            "days": [
                {
                    "day": d.day_number,
                    "title": d.day_title,
                    "location": d.location_name,
                    "description": d.long_description or d.short_description or "",
                    "meals": d.meals_included,
                    "transport": d.transport_type,
                }
                for d in days
            ],
        }
        generate_pdf(pdf_path, itinerary_data)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Itinerary PDF could not be generated")
    return str(pdf_path), filename
