import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ACTIVE_STATUSES = {"active", "inactive"}
TOUR_STATUSES = {"draft", "published", "unpublished", "disabled"}
TOUR_VISIBILITIES = {"public", "private", "unlisted"}
TOUR_PRICING_TYPES = {"per_person", "per_couple", "per_group", "per_room", "custom_quote"}


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


class StatePayload(BaseModel):
    country_id: int
    state_name: str = Field(min_length=1, max_length=150)
    state_code: str = Field(default="", max_length=10)
    status: str = Field(default="active", max_length=20)

    @field_validator("state_name", "state_code", "status")
    @classmethod
    def trim_text(cls, value: str):
        return value.strip()


class CityPayload(BaseModel):
    country_id: int
    state_id: int | None = None
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
    state_id: int | None = None
    city_id: int | None = None
    category_id: int | None = None
    subcategory_ids: list[int] = Field(default_factory=list)
    start_location: str = Field(default="", max_length=150)
    finish_location: str = Field(default="", max_length=150)
    number_of_days: int = Field(default=1, ge=1)
    number_of_hours: int | None = Field(default=None, ge=0)
    number_of_nights: int | None = Field(default=None, ge=0)
    max_group_size: int | None = Field(default=None, ge=1)
    min_booking_size: int | None = Field(default=None, ge=1)
    tour_language: str = Field(default="", max_length=100)
    suitable_age_range: str = Field(default="", max_length=100)
    tour_visibility: str = Field(default="public", max_length=20)
    featured: bool = False
    short_description: str = Field(default="", max_length=5000)
    long_description: str = Field(default="", max_length=20000)
    pricing_type: str = Field(default="per_person", max_length=20)
    offer_price: float = Field(default=0, ge=0)
    infant_price: float = Field(default=0, ge=0)
    single_supplement: float = Field(default=0, ge=0)
    tax_percentage: float = Field(default=0, ge=0)
    service_fee: float = Field(default=0, ge=0)
    booking_deposit: float = Field(default=0, ge=0)
    balance_payment_deadline_days: int | None = Field(default=None, ge=0)
    requires_supplier_confirmation: bool = Field(default=True)
    seo_title: str = Field(default="", max_length=180)
    seo_description: str = Field(default="", max_length=255)
    seo_keywords: str = Field(default="", max_length=255)
    focus_keyword: str = Field(default="", max_length=180)
    canonical_url: str = Field(default="", max_length=500)
    open_graph_image: str = Field(default="", max_length=255)
    search_visibility: bool = True
    image_alt_text: str = Field(default="", max_length=180)
    banner_image: str = Field(default="", max_length=255)
    map_image: str = Field(default="", max_length=255)
    mobile_cover_image: str = Field(default="", max_length=255)
    tour_video_url: str = Field(default="", max_length=500)
    brochure_pdf: str = Field(default="", max_length=255)
    status: str = Field(default="draft", max_length=20)
    # Optimistic concurrency: the tour's updated_at the client last saw.
    # When set on an edit (create leaves it None), the server rejects the
    # write with 409 if the tour has changed since -- see save_tour().
    expected_updated_at: Optional[datetime] = None

    @field_validator("title", "slug", "subtitle", "currency", "start_location", "finish_location", "short_description", "long_description", "seo_title", "seo_description", "seo_keywords", "image_alt_text", "banner_image", "map_image", "status", "tour_language", "suitable_age_range", "tour_visibility", "pricing_type", "focus_keyword", "canonical_url", "open_graph_image", "mobile_cover_image", "tour_video_url", "brochure_pdf")
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

    @field_validator("tour_visibility")
    @classmethod
    def validate_visibility(cls, value: str):
        value = value.strip().lower()
        if value not in TOUR_VISIBILITIES:
            raise ValueError("Invalid tour visibility")
        return value

    @field_validator("pricing_type")
    @classmethod
    def validate_pricing_type(cls, value: str):
        value = value.strip().lower()
        if value not in TOUR_PRICING_TYPES:
            raise ValueError("Invalid pricing type")
        return value
