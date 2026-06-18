from typing import Optional
from pydantic import BaseModel, field_validator

BOOKING_STATUSES = {"upcoming", "ongoing", "completed", "cancelled"}
PAYMENT_STATUSES = {"pending", "partial", "paid", "refunded"}


class BookingCreate(BaseModel):
    customer_id: int
    tour_id: Optional[int] = None
    supplier_id: Optional[int] = None
    agent_id: Optional[int] = None
    affiliate_id: Optional[int] = None
    tour_name: str
    tour_date: str
    country: str = ""
    supplier_name: str = ""
    no_of_adults: int = 1
    no_of_children: int = 0
    no_of_infants: int = 0
    total_cost: float = 0.0
    notes: Optional[str] = None

    @field_validator("tour_name")
    @classmethod
    def tour_name_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("tour_name is required")
        return v

    @field_validator("tour_date")
    @classmethod
    def tour_date_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("tour_date is required")
        return v


class BookingUpdate(BaseModel):
    tour_name: Optional[str] = None
    tour_date: Optional[str] = None
    country: Optional[str] = None
    supplier_name: Optional[str] = None
    no_of_adults: Optional[int] = None
    no_of_children: Optional[int] = None
    no_of_infants: Optional[int] = None
    total_cost: Optional[float] = None
    notes: Optional[str] = None
    supplier_id: Optional[int] = None
    agent_id: Optional[int] = None
    affiliate_id: Optional[int] = None


class BookingStatusUpdate(BaseModel):
    booking_status: str

    @field_validator("booking_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in BOOKING_STATUSES:
            raise ValueError(f"booking_status must be one of: {', '.join(sorted(BOOKING_STATUSES))}")
        return v


class BookingCancelRequest(BaseModel):
    reason: Optional[str] = "Cancelled by admin"
