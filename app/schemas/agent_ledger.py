from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class AgentPayoutCreate(BaseModel):
    agent_id: Optional[int] = None
    ledger_ids: Optional[List[int]] = Field(default=None, description="IDs of agent_ledger rows to include in this payout")
    amount: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = None
    payment_method: str = "bank_transfer"
    reference_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return code


class AgentPayoutMarkPaid(BaseModel):
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class AgentPayoutApprove(BaseModel):
    notes: Optional[str] = None


class AgentPayoutReject(BaseModel):
    reason: str = Field(min_length=1, max_length=255)
