from pydantic import BaseModel, Field, field_validator


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
        "phone",
        "address",
    )
    @classmethod
    def trim_required_text(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("Field is required")

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
    current_password: str
    new_password: str
