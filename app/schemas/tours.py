from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

PHYSICAL_RATINGS = {"easy", "moderate", "hard"}
ITEM_STATUSES = {"active", "inactive"}
IMAGE_TYPES = {"gallery", "itinerary", "highlight", "banner", "map"}
MARKUP_TYPES = {"percentage", "fixed"}
CALENDAR_STATUSES = {"available", "unavailable", "sold_out", "blocked"}
DISCOUNT_TYPES = {"percentage", "fixed"}
DISCOUNT_SCOPES = {"tour", "all_tours", "category", "country"}
PRICE_TYPES = {"per_person", "per_booking"}
ADDON_CATEGORIES = {"pickup", "room_upgrade", "dining", "insurance", "extra_activity", "additional_night", "meal", "visa_assistance", "other"}


# overview
class TourOverviewPayload(BaseModel):
    duration_text: str = Field(default="", max_length=100)
    start_location: str = Field(default="", max_length=150)
    end_location: str = Field(default="", max_length=150)
    group_size: str = Field(default="", max_length=100)
    tour_type: str = Field(default="", max_length=100)
    physical_rating: str = Field(default="easy", max_length=20)
    overview_icon_data: list[dict[str, Any]] | None = None
    why_choose_this_tour: str = Field(default="")
    ideal_for: str = Field(default="")
    best_season: str = Field(default="", max_length=150)
    tour_pace: str = Field(default="", max_length=50)
    transportation_summary: str = Field(default="")
    accommodation_summary: str = Field(default="")
    meal_summary: str = Field(default="")

    @field_validator("physical_rating")
    @classmethod
    def validate_rating(cls, v: str):
        if v not in PHYSICAL_RATINGS:
            raise ValueError(f"physical_rating must be one of {PHYSICAL_RATINGS}")
        return v


# itinerary
class ItineraryPayload(BaseModel):
    day_number: int = Field(ge=1)
    day_title: str = Field(default="", max_length=255)
    location_name: str = Field(default="", max_length=255)
    short_description: str = Field(default="")
    long_description: str = Field(default="")
    activities: str = Field(default="")
    accommodation: str = Field(default="", max_length=255)
    start_time: str = Field(default="", max_length=20)
    end_time: str = Field(default="", max_length=20)
    travel_distance: str = Field(default="", max_length=100)
    travel_duration: str = Field(default="", max_length=100)
    transport_type: str = Field(default="", max_length=100)
    meals_included: str = Field(default="", max_length=150)
    important_notes: str = Field(default="")
    image: str = Field(default="", max_length=255)
    image_alt_text: str = Field(default="", max_length=180)
    display_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


class ReorderPayload(BaseModel):
    ordered_ids: list[int]


# inclusion / exclusion
class InclusionPayload(BaseModel):
    icon: str = Field(default="", max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    display_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


ExclusionPayload = InclusionPayload


# highlight
class HighlightPayload(BaseModel):
    image: str = Field(default="", max_length=255)
    title: str = Field(min_length=1, max_length=255)
    short_description: str = Field(default="")
    display_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# similar tours
class SimilarTourPayload(BaseModel):
    similar_tour_id: int
    display_order: int = Field(default=0, ge=0)


# extension
class ExtensionPayload(BaseModel):
    extension_tour_id: int
    extension_title: str = Field(default="", max_length=255)
    extension_note: str = Field(default="")
    extra_price: float = Field(default=0.0, ge=0)
    category: str = Field(default="other", max_length=30)
    display_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", max_length=20)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str):
        if v not in ADDON_CATEGORIES:
            raise ValueError(f"category must be one of {ADDON_CATEGORIES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# gallery
class GalleryImagePayload(BaseModel):
    image_path: str = Field(min_length=1, max_length=255)
    image_title: str = Field(default="", max_length=255)
    image_alt_text: str = Field(default="", max_length=180)
    image_caption: str = Field(default="")
    image_type: str = Field(default="gallery", max_length=30)
    display_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", max_length=20)

    @field_validator("image_type")
    @classmethod
    def validate_type(cls, v: str):
        if v not in IMAGE_TYPES:
            raise ValueError(f"image_type must be one of {IMAGE_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# pricing
class PricingPayload(BaseModel):
    passenger_from: int = Field(ge=1)
    passenger_to: int = Field(ge=1)
    adult_price: float = Field(ge=0)
    child_price: float = Field(default=0.0, ge=0)
    # markup_type/markup_value/final_price/supplier_price are accepted for
    # backward compatibility but are always recomputed server-side from the
    # tour's supplier commission -- see services.tours.create_pricing.
    supplier_price: float = Field(default=0.0, ge=0)
    markup_type: str = Field(default="percentage", max_length=20)
    markup_value: float = Field(default=0.0, ge=0)
    final_price: float = Field(default=0.0, ge=0)
    # Tourvaa's own markup on top of the supplier price -- ignored unless
    # the actor is an admin (see create_pricing/update_pricing).
    admin_markup_type: str = Field(default="percentage", max_length=20)
    admin_markup_value: float = Field(default=0.0, ge=0)
    currency: str = Field(default="USD", max_length=10)
    status: str = Field(default="active", max_length=20)
    # Optional explanation for the audit trail when Admin edits a Supplier's
    # pricing slab on their behalf -- never stored on the slab itself.
    change_reason: str = Field(default="", max_length=500)

    @field_validator("markup_type", "admin_markup_type")
    @classmethod
    def validate_markup(cls, v: str):
        if v not in MARKUP_TYPES:
            raise ValueError(f"markup_type must be one of {MARKUP_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# optional activity
class OptionalActivityPayload(BaseModel):
    activity_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    price_per_person: float = Field(default=0.0, ge=0)
    image: str = Field(default="", max_length=255)
    category: str = Field(default="other", max_length=30)
    status: str = Field(default="active", max_length=20)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str):
        if v not in ADDON_CATEGORIES:
            raise ValueError(f"category must be one of {ADDON_CATEGORIES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# accommodation extra
class AccommodationExtraPayload(BaseModel):
    accommodation_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    extra_price: float = Field(default=0.0, ge=0)
    price_type: str = Field(default="per_person", max_length=20)
    category: str = Field(default="room_upgrade", max_length=30)
    is_default: bool = False
    status: str = Field(default="active", max_length=20)

    @field_validator("price_type")
    @classmethod
    def validate_price_type(cls, v: str):
        if v not in PRICE_TYPES:
            raise ValueError(f"price_type must be one of {PRICE_TYPES}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str):
        if v not in ADDON_CATEGORIES:
            raise ValueError(f"category must be one of {ADDON_CATEGORIES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# calendar
class CalendarPayload(BaseModel):
    tour_date: datetime
    start_date: datetime | None = None
    end_date: datetime | None = None
    available_seats: int = Field(default=0, ge=0)
    booked_seats: int = Field(default=0, ge=0)
    status: str = Field(default="available", max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in CALENDAR_STATUSES:
            raise ValueError(f"status must be one of {CALENDAR_STATUSES}")
        return v


# unavailable date
class UnavailableDatePayload(BaseModel):
    unavailable_date: datetime
    reason: str = Field(default="")


# discount
class DiscountPayload(BaseModel):
    category_id: int | None = None
    country_id: int | None = None
    discount_name: str = Field(min_length=1, max_length=255)
    discount_code: str | None = Field(default=None, max_length=50)
    discount_type: str = Field(max_length=20)
    discount_value: float = Field(ge=0)
    discount_scope: str = Field(default="tour", max_length=20)
    start_date: datetime | None = None
    end_date: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    minimum_booking_amount: float = Field(default=0.0, ge=0)
    status: str = Field(default="active", max_length=20)

    @field_validator("discount_type")
    @classmethod
    def validate_type(cls, v: str):
        if v not in DISCOUNT_TYPES:
            raise ValueError(f"discount_type must be one of {DISCOUNT_TYPES}")
        return v

    @field_validator("discount_scope")
    @classmethod
    def validate_scope(cls, v: str):
        if v not in DISCOUNT_SCOPES:
            raise ValueError(f"discount_scope must be one of {DISCOUNT_SCOPES}")
        return v

    @model_validator(mode="after")
    def validate_percentage_bound(self) -> "DiscountPayload":
        if self.discount_type == "percentage" and self.discount_value > 100:
            raise ValueError("A percentage discount_value cannot exceed 100")
        return self


class GlobalDiscountPayload(DiscountPayload):
    tour_id: int | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# price calculation
class PriceCalculationRequest(BaseModel):
    tour_date: datetime | None = None
    adults_count: int = Field(default=1, ge=1)
    children_count: int = Field(default=0, ge=0)
    optional_activity_ids: list[int] = Field(default_factory=list)
    accommodation_extra_ids: list[int] = Field(default_factory=list)
    tour_extension_ids: list[int] = Field(default_factory=list)
    promo_code: str | None = None
