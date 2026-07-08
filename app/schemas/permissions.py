from pydantic import BaseModel, Field, field_validator
from typing import Optional

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class PermissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=150, pattern=SLUG_PATTERN)
    module: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)
    action: str = Field(default="get", max_length=20)

    @field_validator("name", "slug", "module", "action")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("slug", "module", "action")
    @classmethod
    def normalize_text(cls, value: str):
        return value.strip().lower()


class PermissionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=150, pattern=SLUG_PATTERN)
    module: Optional[str] = Field(default=None, min_length=1, max_length=100, pattern=SLUG_PATTERN)
    action: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None

    @field_validator("name", "slug", "module", "action")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]):
        if value is None:
            return value

        return value.strip()

    @field_validator("slug", "module", "action")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]):
        if value is None:
            return value

        return value.strip().lower()
