from typing import Optional
from pydantic import BaseModel, field_validator

PAYMENT_METHODS = {"card", "upi", "bank_transfer", "cash", "other"}
PAYMENT_TYPES = {"advance", "partial", "full", "refund"}
PAYMENT_STATUSES = {"pending", "partial", "paid", "failed", "refunded"}


class PaymentCreate(BaseModel):
    booking_id: int
    customer_id: int
    payment_method: str = "card"
    payment_type: str = "advance"
    total_amount: float
    paid_amount: float
    gst_amount: float = 0.0
    transaction_id: Optional[str] = None
    payment_date: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("payment_method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of: {', '.join(sorted(PAYMENT_METHODS))}")
        return v

    @field_validator("payment_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in PAYMENT_TYPES:
            raise ValueError(f"payment_type must be one of: {', '.join(sorted(PAYMENT_TYPES))}")
        return v


class PaymentUpdate(BaseModel):
    payment_method: Optional[str] = None
    payment_type: Optional[str] = None
    paid_amount: Optional[float] = None
    gst_amount: Optional[float] = None
    transaction_id: Optional[str] = None
    payment_date: Optional[str] = None
    notes: Optional[str] = None


class PaymentStatusUpdate(BaseModel):
    payment_status: str

    @field_validator("payment_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in PAYMENT_STATUSES:
            raise ValueError(f"payment_status must be one of: {', '.join(sorted(PAYMENT_STATUSES))}")
        return v


class RefundRequest(BaseModel):
    amount: float
    reason: Optional[str] = "Refund issued by admin"
