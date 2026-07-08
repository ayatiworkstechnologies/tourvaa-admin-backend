from pydantic import BaseModel, Field, field_validator

from app.utils.operations import ACTIVE_STATUSES, APPROVAL_STATUSES, VALUE_TYPES


class AgentCreate(BaseModel):
    agent_name: str = Field(min_length=1, max_length=150)
    agent_type: str = Field(default="", max_length=75)
    country_id: int | None = None
    city_id: int | None = None
    years_in_operation: int = Field(default=0, ge=0)
    status: str = Field(default="inactive", max_length=20)
    approval_status: str = Field(default="pending", max_length=30)

    @field_validator("agent_name", "agent_type", "status", "approval_status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.lower()
        if value not in ACTIVE_STATUSES:
            raise ValueError("Invalid agent status")
        return value

    @field_validator("approval_status")
    @classmethod
    def validate_approval_status(cls, value: str):
        value = value.lower()
        if value not in APPROVAL_STATUSES:
            raise ValueError("Invalid approval status")
        return value


class AgentContactUpdate(BaseModel):
    contact_name: str | None = Field(default=None, max_length=150)
    designation: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=150)
    alternate_phone: str | None = Field(default=None, max_length=30)

    @field_validator("contact_name", "designation", "phone", "email", "alternate_phone")
    @classmethod
    def trim_optional_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class AgentBusinessInfoUpdate(BaseModel):
    years_in_business: int | None = Field(default=None, ge=0)
    certificate_of_incorporation: str | None = Field(default=None, max_length=255)
    monthly_customers_count: int | None = Field(default=None, ge=0)
    target_market: str | None = Field(default=None, max_length=255)
    destinations_sold: str | None = None
    iata_registration_number: str | None = Field(default=None, max_length=100)
    gst_tax_number: str | None = Field(default=None, max_length=100)

    @field_validator("certificate_of_incorporation", "target_market", "destinations_sold", "iata_registration_number", "gst_tax_number")
    @classmethod
    def trim_optional_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class AgentInvoicingUpdate(BaseModel):
    contact_name: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    account_name: str | None = Field(default=None, max_length=150)
    account_number: str | None = Field(default=None, max_length=100)
    bank_name: str | None = Field(default=None, max_length=150)
    bank_branch: str | None = Field(default=None, max_length=150)
    swift_code: str | None = Field(default=None, max_length=50)
    iban: str | None = Field(default=None, max_length=100)
    country_id: int | None = None
    tax_number: str | None = Field(default=None, max_length=100)

    @field_validator("contact_name", "email", "phone", "account_name", "account_number", "bank_name", "bank_branch", "swift_code", "iban", "tax_number")
    @classmethod
    def trim_optional_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class AgentUpdate(BaseModel):
    agent_name: str | None = Field(default=None, max_length=150)
    agent_type: str | None = Field(default=None, max_length=75)
    country_id: int | None = None
    city_id: int | None = None
    years_in_operation: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=20)
    admin_comments: str | None = Field(default=None, max_length=5000)
    contact: AgentContactUpdate | None = None
    business_info: AgentBusinessInfoUpdate | None = None
    invoicing: AgentInvoicingUpdate | None = None

    @field_validator("agent_name", "agent_type", "status", "admin_comments")
    @classmethod
    def trim_optional_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class AgentDiscountRequest(BaseModel):
    discount_type: str = Field(max_length=20)
    discount_value: float = Field(ge=0)

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, value: str):
        value = value.strip().lower()
        if value not in VALUE_TYPES:
            raise ValueError("Invalid discount type")
        return value
