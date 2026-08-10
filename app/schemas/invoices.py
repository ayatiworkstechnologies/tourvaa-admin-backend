from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class InvoiceGenerateRequest(BaseModel):
    booking_id: int
    payment_id: Optional[int] = None
    invoice_type: Literal["auto", "tax_invoice", "full_payment", "partial_payment"] = "auto"
    gst_rate: Decimal = Field(default=Decimal("0.18"), ge=0, le=1)
    balance_due_date: Optional[datetime] = None


class InvoiceEmailRequest(BaseModel):
    email: Optional[EmailStr] = None
    message: Optional[str] = Field(default=None, max_length=2000)
