from typing import Optional
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

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


class UnifiedRegisterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: str
    first_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    country_code: str = Field(min_length=2, max_length=8)
    mobile_number: str = Field(min_length=6, max_length=20)
    accepted_terms: bool
    redirect: Optional[str] = None

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, value: str):
        value = value.strip().upper()
        if value not in {"CUSTOMER", "AGENT", "SUPPLIER"}:
            raise ValueError("Choose a valid account type")
        return value

    @field_validator("first_name", "country_code", "mobile_number")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_unified_email(cls, value: EmailStr):
        return str(value).strip().lower()

    @model_validator(mode="after")
    def validate_registration(self):
        if not self.accepted_terms:
            raise ValueError("You must accept the Terms and Privacy Policy")
        country_code = self.country_code if self.country_code.startswith("+") else f"+{self.country_code}"
        mobile = re.sub(r"\D", "", self.mobile_number)
        if not PHONE_PATTERN.fullmatch(f"{country_code}{mobile}"):
            raise ValueError("Enter a valid mobile number")
        self.country_code = country_code
        self.mobile_number = mobile
        if self.redirect and (not self.redirect.startswith("/") or self.redirect.startswith("//")):
            raise ValueError("Invalid redirect path")
        return self


class LoginSchema(BaseModel):
    identifier: Optional[str] = None
    email: Optional[str] = None
    password: str
    client_type: Optional[str] = "web"
    device_id: Optional[str] = None
    device_name: Optional[str] = None

    @field_validator("identifier", "email")
    @classmethod
    def normalize_identifier(cls, value: Optional[str]):
        return value.strip().lower() if value else value

    @model_validator(mode="after")
    def require_identifier(self):
        if not (self.identifier or self.email):
            raise ValueError("Email or mobile number is required")
        return self

    @property
    def login_identifier(self) -> str:
        return (self.identifier or self.email or "").strip().lower()


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


class CompleteRegistrationSchema(VerifyEmailSchema):
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str):
        return validate_strong_password(value)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ResendVerificationSchema(BaseModel):
    email: EmailStr
    redirect: Optional[str] = None

    @field_validator("email")
    @classmethod
    def normalize_resend_email(cls, value: EmailStr):
        return str(value).strip().lower()


class ChangeRegistrationEmailSchema(BaseModel):
    change_token: str = Field(min_length=1)
    email: EmailStr
    redirect: Optional[str] = None

    @field_validator("email")
    @classmethod
    def normalize_changed_email(cls, value: EmailStr):
        return str(value).strip().lower()


class ForceLogoutSchema(BaseModel):
    user_id: Optional[int] = None

