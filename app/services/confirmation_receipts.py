"""Private, reproducible booking-confirmation receipts."""
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_private_docs_root
from app.models.bookings import Booking, BookingTraveller
from app.models.payments import Payment
from app.utils.pdf_fallback import write_text_pdf


def _receipt_path(booking: Booking) -> Path:
    folder = get_private_docs_root().joinpath("booking-confirmations")
    folder.mkdir(parents=True, exist_ok=True)
    return folder.joinpath(f"booking-confirmation-{booking.id}.pdf")


def _policy_summary(db: Session, booking: Booking) -> str:
    from app.services.bookings import _cancellation_policy_summary
    return _cancellation_policy_summary(db, booking) or "Please refer to the cancellation terms accepted with this booking."


def generate_confirmation_receipt(db: Session, booking_id: int) -> tuple[Path, str]:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    travellers = db.query(BookingTraveller).filter(BookingTraveller.booking_id == booking.id).order_by(BookingTraveller.id.asc()).all()
    payments = db.query(Payment).filter(Payment.booking_id == booking.id).order_by(Payment.id.asc()).all()
    lines = [
        "TOURVAA BOOKING CONFIRMATION RECEIPT", "",
        "Tour Details", f"Booking code: {booking.booking_code or booking.id}", f"Tour: {booking.tour_name or '-'}",
        f"Status: Booking Confirmed", "",
        "Travel Details", f"Travel date: {booking.tour_date or '-'}", f"Country: {booking.country or '-'}", "",
        "Passenger Details",
    ]
    passenger_lines = []
    for row in travellers:
        name = getattr(row, "full_name", None) or f"{getattr(row, 'first_name', '')} {getattr(row, 'last_name', '')}".strip() or "Traveller"
        passenger_lines.append(f"- {name} ({getattr(row, 'traveller_type', 'traveller')})")
    lines.extend(passenger_lines or ["- No passenger details recorded"])
    lines.extend(["", "Payment Details", f"Total: {booking.currency or ''} {booking.final_amount or booking.total_cost or 0}", f"Paid: {booking.currency or ''} {booking.amount_paid or 0}"])
    lines.extend([f"- {payment.payment_method or payment.gateway or 'Payment'}: {payment.payment_status or '-'} ({payment.payment_code or payment.id})" for payment in payments] or ["- No payment record available"])
    lines.extend(["", "Cancellation Policy", _policy_summary(db, booking)])
    path = _receipt_path(booking)
    write_text_pdf(path, lines)
    return path, f"booking-confirmation-{booking.booking_code or booking.id}.pdf"


def download_confirmation_receipt(db: Session, booking_id: int, actor) -> tuple[str, str]:
    from app.services.bookings import get_booking_by_id
    get_booking_by_id(db, booking_id, actor=actor)
    path, filename = generate_confirmation_receipt(db, booking_id)
    return str(path), filename

