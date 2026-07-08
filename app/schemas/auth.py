from typing import Optional
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,19}$")
STRONG_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")


def validate_strong_password(value: str) -> str:
    if not STRONG_PASSWORD_PATTERN.fullmatch(value):
        raise ValueError(
            "Password must be at least 8 characters and include uppercase, lowercase, number, and special character"
        )
    return value


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


class LoginSchema(BaseModel):
    email: EmailStr
    password: str
    client_type: Optional[str] = "web"
    device_id: Optional[str] = None
    device_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr):
        return str(value).strip().lower()


class ForgotPasswordSchema(BaseModel):
    email: EmailStr
    client_type: Optional[str] = "web"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr):
        return str(value).strip().lower()


class ResetPasswordSchema(BaseModel):
    token: str
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str):
        return validate_strong_password(value)


class RefreshTokenSchema(BaseModel):
    client_type: Optional[str] = "web"
    device_id: Optional[str] = None


class VerifyEmailSchema(BaseModel):
    token: str = Field(min_length=1)


class ForceLogoutSchema(BaseModel):
    user_id: Optional[int] = None

