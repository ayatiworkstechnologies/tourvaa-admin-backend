from typing import Any, Dict, Optional
from pydantic import BaseModel


class CheckoutStart(BaseModel):
    tour_id: int
    tour_calendar_id: Optional[int] = None
    # Carry an existing session key to resume (e.g., after login redirect)
    session_key: Optional[str] = None


class CheckoutUpdate(BaseModel):
    step: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class CheckoutConfirm(BaseModel):
    """Final confirmation — creates the actual booking from the session."""
    notes: Optional[str] = None
    promo_code: Optional[str] = None
