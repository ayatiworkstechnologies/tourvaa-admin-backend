from typing import Optional

from pydantic import BaseModel, Field, field_validator

KEY_PATTERN = r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$"


class EmailTemplateCreate(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=150)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    is_active: bool = True

    @field_validator("key", "name", "subject", "body")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str):
        return value.strip().lower()


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    subject: Optional[str] = Field(default=None, min_length=1, max_length=200)
    body: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    is_active: Optional[bool] = None

    @field_validator("name", "subject", "body")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]):
        if value is None:
            return value

        return value.strip()
