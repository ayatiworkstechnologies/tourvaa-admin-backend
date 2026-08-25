from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import validate_strong_password
from app.utils.operations import ACTIVE_STATUSES, APPROVAL_STATUSES


class AffiliateCreate(BaseModel):
    business_type: str = Field(default="", max_length=75)
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str | None = Field(default=None, min_length=8)
    phone: str = Field(default="", max_length=30)
    website_url: str = Field(default="", max_length=255)
    country_id: int | None = None
    city_id: int | None = None
    status: str = Field(default="inactive", max_length=20)
    approval_status: str = Field(default="pending", max_length=30)
    commission_percentage: float = Field(default=0, ge=0, le=100)

    @field_validator("business_type", "name", "phone", "website_url", "status", "approval_status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr):
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None):
        return validate_strong_password(value) if value is not None else value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.lower()
        if value not in ACTIVE_STATUSES:
            raise ValueError("Invalid affiliate status")
        return value

    @field_validator("approval_status")
    @classmethod
    def validate_approval_status(cls, value: str):
        value = value.lower()
        if value not in APPROVAL_STATUSES:
            raise ValueError("Invalid approval status")
        return value


class AffiliateMarketingInfoUpdate(BaseModel):
    promotion_methods: str | None = Field(default=None)
    estimated_monthly_bookings: int | None = Field(default=None, ge=0)
    existing_audience_size: int | None = Field(default=None, ge=0)
    social_media_profiles: str | None = Field(default=None)
    existing_travel_platforms_used: str | None = Field(default=None)


class AffiliateInvoicingUpdate(BaseModel):
    contact_name: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    account_name: str | None = Field(default=None, max_length=150)
    account_number: str | None = Field(default=None, max_length=100)
    bank_name: str | None = Field(default=None, max_length=150)
    country_id: int | None = None
    tax_number: str | None = Field(default=None, max_length=100)


class AffiliateUpdate(BaseModel):
    business_type: str | None = Field(default=None, max_length=75)
    name: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    website_url: str | None = Field(default=None, max_length=255)
    country_id: int | None = None
    city_id: int | None = None
    status: str | None = Field(default=None, max_length=20)
    admin_comments: str | None = Field(default=None, max_length=5000)
    commission_percentage: float | None = Field(default=None, ge=0, le=100)
    marketing_info: AffiliateMarketingInfoUpdate | None = None
    invoicing: AffiliateInvoicingUpdate | None = None


class AffiliateSelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Self-service fields only -- status, admin_comments, and
    # commission_percentage are deliberately excluded. Unlike Supplier's
    # commission (a floor a supplier may self-raise), an affiliate's
    # commission is a platform-paid ceiling set by an admin (see
    # app/services/settings.py get_affiliate_default_commission /
    # affiliate_commission_max_percentage) -- there is no self-raise
    # precedent to mirror here.
    name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    website_url: str | None = Field(default=None, max_length=255)
    country_id: int | None = None
    city_id: int | None = None
    marketing_info: AffiliateMarketingInfoUpdate | None = None
    invoicing: AffiliateInvoicingUpdate | None = None

    @field_validator("name", "phone", "website_url")
    @classmethod
    def trim_self_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class AffiliateDocumentReviewRequest(BaseModel):
    status: str = Field(max_length=20)
    rejection_reason: str | None = Field(default=None, max_length=255)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in {"approved", "rejected"}:
            raise ValueError("Status must be 'approved' or 'rejected'")
        return value


class AffiliateSuspendRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AffiliateApiLinkRequest(BaseModel):
    api_link: str = Field(max_length=255)

    @field_validator("api_link")
    @classmethod
    def trim_link(cls, value: str):
        return value.strip()
