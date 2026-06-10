from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterSchema(BaseModel):
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


class LoginSchema(BaseModel):
    email: EmailStr
    password: str
    client_type: Optional[str] = "web"
    device_id: Optional[str] = None
    device_name: Optional[str] = None


class ForgotPasswordSchema(BaseModel):
    email: EmailStr
    client_type: Optional[str] = "web"


class ResetPasswordSchema(BaseModel):
    token: str
    password: str = Field(min_length=8)
