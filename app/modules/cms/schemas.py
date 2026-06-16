import re

from pydantic import BaseModel, Field, field_validator

ACTIVE_STATUSES = {"active", "inactive"}
TOUR_STATUSES = {"draft", "published", "unpublished", "disabled"}


def slugify(value: str):
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "item"


class StatusUpdate(BaseModel):
    status: str = Field(max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in ACTIVE_STATUSES and value not in TOUR_STATUSES:
            raise ValueError("Invalid status")
        return value


class CountryPayload(BaseModel):
    country_name: str = Field(min_length=1, max_length=120)
    country_code: str = Field(min_length=1, max_length=10)
    phone_code: str = Field(default="", max_length=10)
    currency_code: str = Field(default="", max_length=10)
    status: str = Field(default="active", max_length=20)

    @field_validator("country_name", "country_code", "phone_code", "currency_code", "status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class CityPayload(BaseModel):
    country_id: int
    city_name: str = Field(min_length=1, max_length=120)
    status: str = Field(default="active", max_length=20)

    @field_validator("city_name", "status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class CategoryPayload(BaseModel):
    category_name: str = Field(min_length=1, max_length=120)
    slug: str = Field(default="", max_length=150)
    description: str = Field(default="", max_length=5000)
    image: str = Field(default="", max_length=255)
    status: str = Field(default="active", max_length=20)

    @field_validator("category_name", "slug", "description", "image", "status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class SubcategoryPayload(BaseModel):
    category_id: int
    subcategory_name: str = Field(min_length=1, max_length=120)
    slug: str = Field(default="", max_length=150)
    description: str = Field(default="", max_length=5000)
    image: str = Field(default="", max_length=255)
    status: str = Field(default="active", max_length=20)

    @field_validator("subcategory_name", "slug", "description", "image", "status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class TourPayload(BaseModel):
    supplier_id: int | None = None
    title: str = Field(min_length=1, max_length=180)
    slug: str = Field(default="", max_length=200)
    subtitle: str = Field(default="", max_length=255)
    price_start_per_person: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", max_length=10)
    country_id: int | None = None
    city_id: int | None = None
    category_id: int | None = None
    subcategory_ids: list[int] = Field(default_factory=list)
    start_location: str = Field(default="", max_length=150)
    finish_location: str = Field(default="", max_length=150)
    number_of_days: int = Field(default=1, ge=1)
    number_of_hours: int | None = Field(default=None, ge=0)
    short_description: str = Field(default="", max_length=5000)
    long_description: str = Field(default="", max_length=20000)
    seo_title: str = Field(default="", max_length=180)
    seo_description: str = Field(default="", max_length=255)
    seo_keywords: str = Field(default="", max_length=255)
    image_alt_text: str = Field(default="", max_length=180)
    banner_image: str = Field(default="", max_length=255)
    map_image: str = Field(default="", max_length=255)
    status: str = Field(default="draft", max_length=20)

    @field_validator("title", "slug", "subtitle", "currency", "start_location", "finish_location", "short_description", "long_description", "seo_title", "seo_description", "seo_keywords", "image_alt_text", "banner_image", "map_image", "status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        if value not in TOUR_STATUSES:
            raise ValueError("Invalid tour status")
        return value
