import re

from pydantic import BaseModel, Field, field_validator

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,19}$")


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=1, max_length=30)
    profile_image: str = Field(default="", max_length=255)
    address: str = Field(min_length=1, max_length=255)
    country: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    pincode: str = Field(default="", max_length=20)

    @field_validator(
        "name",
        "address",
    )
    @classmethod
    def trim_required_text(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("Field is required")

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("Field is required")

        if not PHONE_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid mobile number")

        return value

    @field_validator(
        "profile_image",
        "country",
        "state",
        "city",
        "pincode",
    )
    @classmethod
    def trim_optional_text(cls, value: str):
        return value.strip()


class PasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str):
        if not re.search(r"[A-Z]", value):
            raise ValueError("New password must include an uppercase letter")

        if not re.search(r"[a-z]", value):
            raise ValueError("New password must include a lowercase letter")

        if not re.search(r"\d", value):
            raise ValueError("New password must include a number")

        return value
