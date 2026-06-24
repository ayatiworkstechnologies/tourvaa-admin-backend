from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class SupplierPayoutCreate(BaseModel):
    supplier_id: int
    ledger_ids: List[int] = Field(..., min_length=1, description="IDs of supplier_ledger rows to include in this payout")
    payment_method: str = "bank_transfer"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class SupplierPayoutMarkPaid(BaseModel):
    reference_number: Optional[str] = None
    notes: Optional[str] = None
