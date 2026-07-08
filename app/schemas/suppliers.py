from pydantic import BaseModel, Field, field_validator

from app.utils.operations import ACTIVE_STATUSES, APPROVAL_STATUSES, VALUE_TYPES


class SupplierCreate(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=150)
    supplier_type: str = Field(default="", max_length=75)
    country_id: int | None = None
    city_id: int | None = None
    years_in_operation: int = Field(default=0, ge=0)
    status: str = Field(default="inactive", max_length=20)
    approval_status: str = Field(default="pending", max_length=30)

    @field_validator("supplier_name", "supplier_type", "status", "approval_status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.lower()
        if value not in ACTIVE_STATUSES:
            raise ValueError("Invalid supplier status")
        return value

    @field_validator("approval_status")
    @classmethod
    def validate_approval_status(cls, value: str):
        value = value.lower()
        if value not in APPROVAL_STATUSES:
            raise ValueError("Invalid approval status")
        return value


class SupplierContactUpdate(BaseModel):
    contact_name: str | None = Field(default=None, max_length=150)
    designation: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=150)
    alternate_phone: str | None = Field(default=None, max_length=30)

class SupplierBusinessInfoUpdate(BaseModel):
    years_in_business: int | None = Field(default=None, ge=0)
    certificate_of_incorporation: str | None = Field(default=None, max_length=255)
    monthly_customers_count: int | None = Field(default=None, ge=0)
    target_market: str | None = Field(default=None, max_length=255)
    destinations_sold: str | None = Field(default=None)
    gst_tax_number: str | None = Field(default=None, max_length=100)
    business_registration_number: str | None = Field(default=None, max_length=100)

class SupplierInvoicingUpdate(BaseModel):
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

class SupplierUpdate(BaseModel):
    supplier_name: str | None = Field(default=None, max_length=150)
    supplier_type: str | None = Field(default=None, max_length=75)
    country_id: int | None = None
    city_id: int | None = None
    years_in_operation: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=20)
    admin_comments: str | None = Field(default=None, max_length=5000)
    contact: SupplierContactUpdate | None = None
    business_info: SupplierBusinessInfoUpdate | None = None
    invoicing: SupplierInvoicingUpdate | None = None

    @field_validator("supplier_name", "supplier_type", "status", "admin_comments")
    @classmethod
    def trim_optional_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None):
        if value is None:
            return value
        value = value.lower()
        if value not in ACTIVE_STATUSES:
            raise ValueError("Invalid supplier status")
        return value


class VehicleCreate(BaseModel):
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(default="", max_length=100)
    vehicle_type: str = Field(default="", max_length=75)
    registration_number: str = Field(default="", max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)
    capacity: int | None = Field(default=None, ge=1)

    @field_validator("make", "model", "vehicle_type", "registration_number")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class VehicleUpdate(BaseModel):
    make: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    vehicle_type: str | None = Field(default=None, max_length=75)
    registration_number: str | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)
    capacity: int | None = Field(default=None, ge=1)

    @field_validator("make", "model", "vehicle_type", "registration_number")
    @classmethod
    def trim_optional_text(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class DocumentReviewRequest(BaseModel):
    status: str = Field(max_length=20)
    rejection_reason: str | None = Field(default=None, max_length=255)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in {"approved", "rejected"}:
            raise ValueError("Status must be 'approved' or 'rejected'")
        return value

    @field_validator("rejection_reason")
    @classmethod
    def trim_reason(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class VehicleReviewRequest(BaseModel):
    approval_status: str = Field(max_length=20)
    rejection_reason: str | None = Field(default=None, max_length=255)

    @field_validator("approval_status")
    @classmethod
    def validate_approval_status(cls, value: str):
        value = value.strip().lower()
        if value not in {"approved", "rejected"}:
            raise ValueError("Approval status must be 'approved' or 'rejected'")
        return value

    @field_validator("rejection_reason")
    @classmethod
    def trim_reason(cls, value: str | None):
        return value.strip() if isinstance(value, str) else value


class SupplierMarkupRequest(BaseModel):
    markup_type: str = Field(max_length=20)
    markup_value: float = Field(ge=0)

    @field_validator("markup_type")
    @classmethod
    def validate_markup_type(cls, value: str):
        value = value.strip().lower()
        if value not in VALUE_TYPES:
            raise ValueError("Invalid markup type")
        return value
