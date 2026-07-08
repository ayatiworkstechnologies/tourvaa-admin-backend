from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.operations import ACTIVE_STATUSES, APPROVAL_STATUSES


class AffiliateCreate(BaseModel):
    business_type: str = Field(default="", max_length=75)
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    website_url: str = Field(default="", max_length=255)
    country_id: int | None = None
    city_id: int | None = None
    status: str = Field(default="inactive", max_length=20)
    approval_status: str = Field(default="pending", max_length=30)

    @field_validator("business_type", "name", "phone", "website_url", "status", "approval_status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr):
        return str(value).strip().lower()

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


class AffiliateApiLinkRequest(BaseModel):
    api_link: str = Field(max_length=255)

    @field_validator("api_link")
    @classmethod
    def trim_link(cls, value: str):
        return value.strip()
