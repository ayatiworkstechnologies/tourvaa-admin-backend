from typing import Optional
from pydantic import BaseModel


class AffiliateLinkCreate(BaseModel):
    label: Optional[str] = None
    destination_url: Optional[str] = None


class AffiliatePayoutCreate(BaseModel):
    affiliate_id: int
    conversion_ids: list[int]
    payment_method: str = "bank_transfer"
    reference_number: Optional[str] = None
    notes: Optional[str] = None
