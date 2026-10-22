from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class CheckoutStart(BaseModel):
    tour_id: int
    tour_calendar_id: Optional[int] = None
    # Preserve the exact departure selected on the tour page when no calendar
    # row is available (or while a session is resumed).
    travel_date: Optional[str] = None
    # Carry an existing session key to resume (e.g., after login redirect)
    session_key: Optional[str] = None


class CheckoutUpdate(BaseModel):
    step: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class CheckoutConfirm(BaseModel):
    """Final confirmation - creates the actual booking from the session."""
    notes: Optional[str] = None
    promo_code: Optional[str] = None
    # Required by services.bookings.create_booking's _validate_agreements for
    # customer/agent bookings - without these the checkout flow can never
    # actually confirm a booking, regardless of what the frontend UI shows.
    agreed_terms: bool = False
    agreed_cancellation_policy: bool = False
    # The customer choice must cross the booking-creation boundary.  The
    # gateway amount is then derived server-side from the saved booking,
    # rather than being reconstructed from browser state after confirmation.
    payment_type: Literal["partial", "full"] = "full"
    # Currency currently shown to the customer. It is converted and locked
    # server-side when the booking is created, never trusted as an amount.
    display_currency: Optional[str] = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
