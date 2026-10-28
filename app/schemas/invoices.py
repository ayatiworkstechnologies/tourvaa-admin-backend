from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class InvoiceGenerateRequest(BaseModel):
    booking_id: int
    payment_id: Optional[int] = None
    invoice_type: Literal["auto", "tax_invoice", "full_payment", "partial_payment", "agent_reservation_invoice", "deposit_receipt", "payment_receipt"] = "auto"
    # Tax must be explicitly configured by Tourvaa's legal/finance team.  A
    # guessed 18% tax rate is worse than a zero rate on a draft document.
    gst_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    balance_due_date: Optional[datetime] = None


class InvoiceEmailRequest(BaseModel):
    email: Optional[EmailStr] = None
    message: Optional[str] = Field(default=None, max_length=2000)
