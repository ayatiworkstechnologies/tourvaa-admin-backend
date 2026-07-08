from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator

PAYMENT_METHODS = {"card", "upi", "bank_transfer", "cash", "other"}
PAYMENT_TYPES = {"advance", "partial", "full", "refund"}
PAYMENT_STATUSES = {"pending", "authorized", "partially_paid", "paid", "failed", "refunded", "partially_refunded", "voided", "partial"}


class PaymentCreate(BaseModel):
    booking_id: int
    customer_id: int
    payment_method: str = "card"
    payment_type: str = "full"
    total_amount: Decimal
    paid_amount: Decimal = Decimal("0")
    gst_amount: Decimal = Decimal("0")
    surcharge_amount: Decimal = Decimal("0")
    gateway: str = "manual"
    gateway_payment_id: Optional[str] = None
    gateway_order_id: Optional[str] = None
    idempotency_key: Optional[str] = None
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


class PaymentAuthorize(BaseModel):
    booking_id: int
    amount: Decimal = Field(gt=0)
    payment_method: str = "card"
    payment_type: str = "full"
    gateway: str = "manual"
    gateway_payment_id: Optional[str] = None
    gateway_order_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    notes: Optional[str] = None


class PaymentCapture(BaseModel):
    amount: Decimal = Field(gt=0)
    transaction_id: Optional[str] = None
    notes: Optional[str] = None


class PaymentVoid(BaseModel):
    reason: Optional[str] = "Payment voided"


class PaymentUpdate(BaseModel):
    payment_method: Optional[str] = None
    payment_type: Optional[str] = None
    paid_amount: Optional[Decimal] = None
    gst_amount: Optional[Decimal] = None
    surcharge_amount: Optional[Decimal] = None
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
    amount: Decimal = Field(gt=0)
    reason: Optional[str] = "Refund issued by admin"
