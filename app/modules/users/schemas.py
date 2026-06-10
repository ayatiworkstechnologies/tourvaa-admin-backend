from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime


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

    @field_validator(
        "phone",
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
        "phone",
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


class UserApprovalUpdate(BaseModel):
    role_id: Optional[int] = None


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
