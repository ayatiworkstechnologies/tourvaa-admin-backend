import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_private_docs_root
from app.models.bookings import Booking
from app.models.tours import TourHighlight, TourItinerary
from app.models.users import User
from app.models.settings import AppSetting
from app.config import settings
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
        .filter(TourItinerary.tour_id == booking.tour_id, TourItinerary.status == "active")
        .order_by(TourItinerary.day_number.asc())
        .all()
    )
    if not days:
        raise HTTPException(status_code=404, detail="No itinerary is available for this tour yet")

    highlights = (
        db.query(TourHighlight)
        .filter(TourHighlight.tour_id == booking.tour_id, TourHighlight.status == "active")
        .order_by(TourHighlight.display_order.asc())
        .all()
    )

    storage = get_private_docs_root().joinpath("itineraries")
    storage.mkdir(parents=True, exist_ok=True)
    # Version the cached artifact so PDFs generated before the contact-footer
    # settings became dynamic are not served indefinitely.
    filename = f"{booking.booking_code or booking.id}-itinerary-v2.pdf"
    pdf_path = storage.joinpath(filename)

    # Older deployments could cache a text fallback under a .pdf filename.
    # Regenerate any missing, empty, or non-PDF cached artifact so every
    # response can be opened by a browser PDF viewer.
    has_valid_pdf = pdf_path.exists() and pdf_path.is_file() and pdf_path.stat().st_size > 5
    if has_valid_pdf:
        try:
            has_valid_pdf = pdf_path.read_bytes()[:5] == b"%PDF-"
        except OSError:
            has_valid_pdf = False
    if not has_valid_pdf:
        support_setting = db.query(AppSetting).filter(AppSetting.key == "support_email").first()
        support_email = (support_setting.value or "").strip() if support_setting else ""
        website = urlparse(settings.FRONTEND_URL or "").netloc or "www.tourvaa.com"
        itinerary_data = {
            "booking_code": booking.booking_code or str(booking.id),
            "tour_name": booking.tour_name or "Tour",
            "customer_name": booking.customer.full_name if booking.customer else "",
            "tour_date": booking.tour_date or "",
            "support_email": support_email,
            "website": website,
            "highlights": [{"title": h.title, "description": h.short_description or ""} for h in highlights],
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

    if not os.path.exists(pdf_path) or not pdf_path.is_file() or pdf_path.stat().st_size <= 5 or pdf_path.read_bytes()[:5] != b"%PDF-":
        raise HTTPException(status_code=404, detail="Itinerary PDF could not be generated")
    return str(pdf_path), filename


def build_public_tour_itinerary_pdf(db: Session, tour) -> tuple[bytes, str]:
    """Render the supplier-maintained itinerary for public viewing/download.

    This deliberately derives the document from structured itinerary days; it
    does not repurpose the optional marketing brochure upload.
    """
    days = db.query(TourItinerary).filter(
        TourItinerary.tour_id == tour.id, TourItinerary.status == "active"
    ).order_by(TourItinerary.day_number.asc()).all()
    if not days:
        raise HTTPException(status_code=404, detail="No itinerary is available for this tour yet")
    highlights = db.query(TourHighlight).filter(
        TourHighlight.tour_id == tour.id, TourHighlight.status == "active"
    ).order_by(TourHighlight.display_order.asc()).all()
    support_setting = db.query(AppSetting).filter(AppSetting.key == "support_email").first()
    support_email = (support_setting.value or "").strip() if support_setting else ""
    website = urlparse(settings.FRONTEND_URL or "").netloc or "www.tourvaa.com"
    data = {
        "public_tour": True,
        "tour_name": tour.title or "Tour",
        "support_email": support_email,
        "website": website,
        "highlights": [{"title": h.title, "description": h.short_description or ""} for h in highlights],
        "days": [{"day": d.day_number, "title": d.day_title, "location": d.location_name,
                  "description": d.long_description or d.short_description or "", "meals": d.meals_included,
                  "transport": d.transport_type} for d in days],
    }
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "itinerary.pdf")
        generate_pdf(Path(path), data)
        content = Path(path).read_bytes()
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=502, detail="Itinerary PDF could not be generated")
    safe_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (tour.slug or f"tour-{tour.id}")).strip("-.")
    return content, f"{safe_slug or f'tour-{tour.id}'}-itinerary.pdf"
