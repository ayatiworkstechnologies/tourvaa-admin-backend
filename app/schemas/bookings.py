from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

BOOKING_STATUSES = {"draft", "pending_payment", "payment_authorized", "pending_supplier_acceptance", "confirmed", "ongoing", "completed", "cancelled", "declined", "refunded", "upcoming", "postponed"}
SUPPLIER_ACCEPTANCE_STATUSES = {"not_assigned", "pending", "accepted", "declined", "expired"}
PAYMENT_STATUSES = {"unpaid", "pending", "authorized", "partially_paid", "paid", "failed", "refunded", "partially_refunded", "voided", "partial"}
PAYMENT_TYPES = {"partial", "full"}
BOOKING_SOURCES = {"customer", "agent", "admin"}
TRAVELLER_TYPES = {"adult", "child"}
CHANGE_SOURCES = {"customer", "agent", "supplier", "admin", "system", "payment_gateway"}


class BookingTravellerPayload(BaseModel):
    traveller_type: str
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    date_of_birth: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry_date: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary_contact: bool = False
    special_requirements: Optional[str] = None

    @field_validator("traveller_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in TRAVELLER_TYPES:
            raise ValueError("Invalid traveller_type")
        return v


class BookingAddonPayload(BaseModel):
    id: Optional[int] = None
    quantity: int = Field(default=1, ge=1)


class BookingCreate(BaseModel):
    customer_id: int
    tour_id: Optional[int] = None
    tour_calendar_id: Optional[int] = None
    supplier_id: Optional[int] = None
    agent_id: Optional[int] = None
    affiliate_id: Optional[int] = None
    booking_source: str = "admin"
    country_id: Optional[int] = None
    city_id: Optional[int] = None
    tour_name: str = ""
    tour_date: str = ""
    tour_start_date: Optional[str] = None
    tour_end_date: Optional[str] = None
    country: str = ""
    supplier_name: str = ""
    no_of_adults: int = Field(default=1, ge=0)
    no_of_children: int = Field(default=0, ge=0)
    no_of_infants: int = Field(default=0, ge=0)
    adults_count: Optional[int] = Field(default=None, ge=0)
    children_count: Optional[int] = Field(default=None, ge=0)
    currency: str = "USD"
    payment_type: str = "full"
    promo_code: Optional[str] = None
    optional_activities: list[BookingAddonPayload] = Field(default_factory=list)
    accommodations: list[BookingAddonPayload] = Field(default_factory=list)
    extensions: list[BookingAddonPayload] = Field(default_factory=list)
    travellers: list[BookingTravellerPayload] = Field(default_factory=list)
    total_cost: Decimal = Decimal("0")
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("booking_source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in BOOKING_SOURCES:
            raise ValueError("Invalid booking_source")
        return v

    @field_validator("payment_type")
    @classmethod
    def validate_payment_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in PAYMENT_TYPES:
            raise ValueError("Invalid payment_type")
        return v


class BookingUpdate(BaseModel):
    tour_name: Optional[str] = None
    tour_date: Optional[str] = None
    country: Optional[str] = None
    supplier_name: Optional[str] = None
    no_of_adults: Optional[int] = None
    no_of_children: Optional[int] = None
    no_of_infants: Optional[int] = None
    total_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None
    supplier_id: Optional[int] = None
    agent_id: Optional[int] = None
    affiliate_id: Optional[int] = None


class BookingStatusUpdate(BaseModel):
    booking_status: str
    reason: Optional[str] = None
    metadata: dict[str, Any] | None = None

    @field_validator("booking_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in BOOKING_STATUSES:
            raise ValueError(f"booking_status must be one of: {', '.join(sorted(BOOKING_STATUSES))}")
        return v


class BookingCancelRequest(BaseModel):
    reason: Optional[str] = "Cancelled by admin"


class AssignSupplierRequest(BaseModel):
    supplier_id: int
    reason: Optional[str] = None


class SupplierDecisionRequest(BaseModel):
    reason: Optional[str] = None


class SupplierPostponeRequest(BaseModel):
    reason: str = Field(min_length=1)
    new_tour_date: Optional[str] = None


class SupplierNotifyRequest(BaseModel):
    message: str = Field(min_length=1)
    notify_customer: bool = True
    notify_agent: bool = True


class BookingCommunicationCreate(BaseModel):
    subject: str = ""
    message: str
    visibility: str = "internal"
    message_type: str = "admin_message"

class MessageReplyCreate(BaseModel):
    message: str
