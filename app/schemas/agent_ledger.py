from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class AgentPayoutCreate(BaseModel):
    agent_id: Optional[int] = None
    ledger_ids: Optional[List[int]] = Field(default=None, description="IDs of agent_ledger rows to include in this payout")
    amount: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = None
    payment_method: str = "bank_transfer"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class AgentPayoutMarkPaid(BaseModel):
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class AgentPayoutApprove(BaseModel):
    notes: Optional[str] = None
