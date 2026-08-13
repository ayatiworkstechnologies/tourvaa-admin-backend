from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class AffiliateLinkCreate(BaseModel):
    link_type: str = "custom"  # tour | custom (category/destination accepted, not yet resolved)
    tour_id: Optional[int] = None
    destination_url: Optional[str] = None
    label: Optional[str] = None
    campaign_name: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    custom_alias: Optional[str] = None
    commission_type_override: Optional[str] = None
    commission_percentage_override: Optional[Decimal] = None
    commission_fixed_override: Optional[Decimal] = None
    attribution_model: str = "last_click"
    attribution_window_days: int = 30
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class AffiliateLinkAdminCreate(AffiliateLinkCreate):
    affiliate_id: int


class AffiliateLinkUpdate(BaseModel):
    label: Optional[str] = None
    destination_url: Optional[str] = None
    campaign_name: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    # Admin-only fields (ignored by the self-service router) -----------------
    commission_type_override: Optional[str] = None
    commission_percentage_override: Optional[Decimal] = None
    commission_fixed_override: Optional[Decimal] = None
    attribution_model: Optional[str] = None
    attribution_window_days: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    status: Optional[str] = None


class AffiliatePayoutCreate(BaseModel):
    affiliate_id: int
    conversion_ids: list[int]
    payment_method: str = "bank_transfer"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class AffiliatePayoutMethodCreate(BaseModel):
    method_type: str = "bank_transfer"
    account_holder_name: Optional[str] = ""
    bank_name: Optional[str] = ""
    account_number: Optional[str] = ""
    ifsc: Optional[str] = ""
    swift_code: Optional[str] = ""
    bank_country: Optional[str] = ""
    paypal_email: Optional[str] = ""
    is_default: bool = False


class AffiliatePayoutMethodUpdate(BaseModel):
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    swift_code: Optional[str] = None
    bank_country: Optional[str] = None
    paypal_email: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class AffiliatePayoutRequestCreate(BaseModel):
    amount: Decimal
    payout_method_id: int
    notes: Optional[str] = None


class AffiliatePayoutReject(BaseModel):
    reason: str


class AffiliatePayoutMarkPaid(BaseModel):
    payment_reference: str
    admin_notes: Optional[str] = None


class AffiliateCommissionRuleCreate(BaseModel):
    name: Optional[str] = None
    affiliate_id: Optional[int] = None
    tour_id: Optional[int] = None
    category_id: Optional[int] = None
    affiliate_link_id: Optional[int] = None
    commission_type: str = "percentage"
    percentage: Decimal = Decimal("0")
    fixed_amount: Decimal = Decimal("0")
    currency: str = "USD"
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    priority: int = 0
    is_active: bool = True


class AffiliateCommissionRuleUpdate(BaseModel):
    name: Optional[str] = None
    commission_type: Optional[str] = None
    percentage: Optional[Decimal] = None
    fixed_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
