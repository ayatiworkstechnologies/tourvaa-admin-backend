from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class InvoiceGenerateRequest(BaseModel):
    booking_id: int
    payment_id: Optional[int] = None
    invoice_type: str = "tax_invoice"
    gst_rate: Decimal = Decimal("0.18")


class InvoiceEmailRequest(BaseModel):
    email: Optional[str] = None
    message: Optional[str] = None
