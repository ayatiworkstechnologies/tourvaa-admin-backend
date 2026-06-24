from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class CancellationRequestCreate(BaseModel):
    booking_id: int
    reason: str


class CancellationApprove(BaseModel):
    refund_percentage: Optional[Decimal] = None
    refund_amount: Optional[Decimal] = None
    admin_notes: Optional[str] = None


class CancellationReject(BaseModel):
    admin_notes: str


class RefundRuleCreate(BaseModel):
    tour_id: Optional[int] = None
    days_before_tour_min: int
    days_before_tour_max: Optional[int] = None
    refund_percentage: Decimal
    description: Optional[str] = None


class ProcessRefundBody(BaseModel):
    gateway: str = "manual"
    gateway_refund_id: Optional[str] = None
