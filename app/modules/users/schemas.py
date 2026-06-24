import re

from pydantic import BaseModel, EmailStr, Field, field_validator
from app.modules.auth.schemas import validate_strong_password
from typing import Optional
from datetime import datetime

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,19}$")


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    profile_image: str = Field(default="", max_length=255)
    address: str = Field(default="", max_length=255)
    country: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    pincode: str = Field(default="", max_length=20)
    password: str = Field(min_length=8)
    role_id: Optional[int] = None

    @field_validator("name")
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

    @field_validator(
        "profile_image",
        "address",
        "country",
        "state",
        "city",
        "pincode",
    )
    @classmethod
    def trim_optional_text(cls, value: str):
        return value.strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str):
        value = value.strip()
        if value and not PHONE_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid mobile number")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str):
        return validate_strong_password(value)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    approval_status: Optional[str] = None

    @field_validator(
        "name",
        "profile_image",
        "address",
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

    @field_validator("phone")
    @classmethod
    def validate_optional_phone(cls, value: Optional[str]):
        if value is None:
            return value

        value = value.strip()
        if value and not PHONE_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid mobile number")
        return value

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: Optional[EmailStr]):
        if value is None:
            return value

        return str(value).strip().lower()


class UserApprovalUpdate(BaseModel):
    role_id: Optional[int] = None


class UserRolesUpdate(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    profile_image: str
    address: str
    country: str
    state: str
    city: str
    pincode: str
    role_id: Optional[int] = None
    is_active: bool
    approval_status: str
    created_at: datetime

    class Config:
        from_attributes = True

