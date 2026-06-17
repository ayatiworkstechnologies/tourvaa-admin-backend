import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,19}$")
CUSTOMER_STATUSES = {"active", "inactive", "blocked"}
MESSAGE_TYPES = {"admin_message", "customer_reply", "system_notification"}


class CustomerCreate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=75)
    last_name: Optional[str] = Field(default=None, max_length=75)
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    country_id: Optional[int] = None
    city_id: Optional[int] = None
    address_line_1: str = Field(default="", max_length=255)
    address_line_2: str = Field(default="", max_length=255)
    postal_code: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=255)
    profile_image: str = Field(default="", max_length=255)
    country: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    pincode: str = Field(default="", max_length=20)
    status: str = Field(default="active", max_length=20)

    @field_validator("full_name")
    @classmethod
    def trim_required_text(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr):
        return str(value).strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str):
        value = value.strip()
        if value and not PHONE_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid mobile number")
        return value

    @field_validator(
        "first_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "postal_code",
        "address",
        "profile_image",
        "country",
        "state",
        "city",
        "pincode",
        "status",
    )
    @classmethod
    def trim_optional_text(cls, value: Optional[str]):
        if value is None:
            return value
        return value.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in CUSTOMER_STATUSES:
            raise ValueError("Invalid customer status")
        return value


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=75)
    last_name: Optional[str] = Field(default=None, max_length=75)
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    country_id: Optional[int] = None
    city_id: Optional[int] = None
    address_line_1: Optional[str] = Field(default=None, max_length=255)
    address_line_2: Optional[str] = Field(default=None, max_length=255)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=255)
    profile_image: Optional[str] = Field(default=None, max_length=255)
    country: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=20)

    @field_validator(
        "first_name",
        "last_name",
        "full_name",
        "phone",
        "address_line_1",
        "address_line_2",
        "postal_code",
        "address",
        "profile_image",
        "country",
        "state",
        "city",
        "pincode",
    )
    @classmethod
    def trim_optional_text(cls, value: Optional[str]):
        if value is None:
            return value
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: Optional[EmailStr]):
        if value is None:
            return value
        return str(value).strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_optional_phone(cls, value: Optional[str]):
        if value is None:
            return value
        value = value.strip()
        if value and not PHONE_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid mobile number")
        return value


class CustomerStatusUpdate(BaseModel):
    status: str = Field(max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in {"active", "inactive"}:
            raise ValueError("Invalid customer status")
        return value


class CustomerBlockRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Block reason is required")
        return value


class SendCustomerMessageRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=1, max_length=5000)
    booking_id: Optional[int] = None
    message_type: str = Field(default="admin_message", max_length=30)

    @field_validator("subject", "message", "message_type")
    @classmethod
    def trim_text(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Field is required")
        return value

    @field_validator("message_type")
    @classmethod
    def validate_message_type(cls, value: str):
        value = value.strip()
        if value not in MESSAGE_TYPES:
            raise ValueError("Invalid message type")
        return value
