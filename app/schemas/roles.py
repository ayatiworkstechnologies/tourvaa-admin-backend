from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)

    @field_validator("name", "slug")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str):
        return value.strip().lower()


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=100, pattern=SLUG_PATTERN)
    is_active: Optional[bool] = None

    @field_validator("name", "slug")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]):
        if value is None:
            return value

        return value.strip()

    @field_validator("slug")
    @classmethod
    def normalize_optional_slug(cls, value: Optional[str]):
        if value is None:
            return value

        return value.strip().lower()


class AssignPermissions(BaseModel):
    permission_ids: List[int]
