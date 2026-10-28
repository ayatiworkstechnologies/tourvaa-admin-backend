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
    # A confirmed receipt is an immutable record of what was supplied at
    # confirmation time. Version this artifact so an older, regenerating
    # receipt cannot be served after this behaviour was introduced.
    return folder.joinpath(f"booking-confirmation-{booking.id}-v2.pdf")


def _is_valid_pdf(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 5 and path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def _policy_summary(db: Session, booking: Booking) -> str:
    from app.services.bookings import _cancellation_policy_summary
    return _cancellation_policy_summary(db, booking) or "Please refer to the cancellation terms accepted with this booking."


def generate_confirmation_receipt(db: Session, booking_id: int) -> tuple[Path, str]:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    path = _receipt_path(booking)
    # Do not regenerate a final receipt from mutable tour/policy data. The
    # first generation happens during the booking-confirmation email event,
    # and the same exact document is subsequently downloaded by the customer.
    if _is_valid_pdf(path):
        return path, f"booking-confirmation-{booking.booking_code or booking.id}.pdf"

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
    lines.extend([
        f"- {payment.payment_method or payment.gateway or 'Payment'}: {payment.payment_status or '-'}; "
        f"authorised {booking.currency or ''} {payment.authorized_amount or 0}; "
        f"captured {booking.currency or ''} {payment.captured_amount or payment.paid_amount or 0} "
        f"({payment.payment_code or payment.id})"
        for payment in payments
    ] or ["- No payment record available"])
    lines.extend(["", "Cancellation Policy", _policy_summary(db, booking)])
    write_text_pdf(path, lines)
    return path, f"booking-confirmation-{booking.booking_code or booking.id}.pdf"


def download_confirmation_receipt(db: Session, booking_id: int, actor) -> tuple[str, str]:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.customer or booking.customer.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Booking access denied")
    if (booking.booking_status or "").lower() not in {"confirmed", "ready_to_travel", "upcoming", "ongoing", "completed"}:
        raise HTTPException(status_code=409, detail="A confirmation receipt is available only after the booking is confirmed")
    path, filename = generate_confirmation_receipt(db, booking_id)
    return str(path), filename

