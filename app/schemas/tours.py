from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

PHYSICAL_RATINGS = {"easy", "moderate", "hard"}
ITEM_STATUSES = {"active", "inactive"}
IMAGE_TYPES = {"gallery", "itinerary", "highlight", "banner", "map"}
CALENDAR_STATUSES = {"available", "unavailable", "sold_out", "blocked"}
AVAILABILITY_FREQUENCIES = {"weekly", "fortnightly", "monthly"}
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

    @model_validator(mode="before")
    @classmethod
    def coerce_null_text_fields(cls, data):
        # Several TourOverview DB columns are nullable with no default (see
        # app.models.tours.TourOverview) - existing rows can hold NULL, and
        # the frontend round-trips GET data straight back into this POST/PUT
        # payload, so a None here from an old row is expected, not client
        # error. Treat it the same as "" rather than 422ing.
        if isinstance(data, dict):
            for key in ("why_choose_this_tour", "ideal_for", "best_season", "tour_pace",
                        "transportation_summary", "accommodation_summary", "meal_summary"):
                if data.get(key) is None:
                    data[key] = ""
        return data

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
    optional_activities: str = Field(default="")
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
    # Additional images for the day's carousel, beyond the single cover
    # `image` above - stored server-side as a JSON-encoded string.
    images: list[str] = Field(default_factory=list)
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
    # adult_price/child_price are the supplier's own net asking price -
    # Tourvaa pays the supplier that price in full, no commission is
    # deducted. admin_markup_value is Tourvaa's own commission, an
    # admin-only retail markup added on top of the supplier's price to
    # produce the storefront price; only honoured when the actor is not a
    # supplier. Bounded 5-15% - Tourvaa's commission is always a percentage
    # decided per tour, never a fixed amount or supplier-negotiated rate.
    # supplier_price/final_price are legacy/unused, kept for backward
    # compatibility only.
    supplier_price: float = Field(default=0.0, ge=0)
    final_price: float = Field(default=0.0, ge=0)
    admin_markup_value: float = Field(default=10.0, ge=5, le=15)
    currency: str = Field(default="USD", max_length=10)
    status: str = Field(default="active", max_length=20)
    # Optional explanation for the audit trail when Admin edits a Supplier's
    # pricing slab on their behalf -- never stored on the slab itself.
    change_reason: str = Field(default="", max_length=500)

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
    image: str = Field(default="", max_length=255)
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


# recurring availability schedule
class AvailabilityConfigPayload(BaseModel):
    availability_start_date: datetime | None = None
    availability_end_date: datetime | None = None
    min_advance_booking_days: int = Field(default=0, ge=0)
    frequency: str | None = None
    frequency_week: int | None = Field(default=None, ge=1, le=4)
    frequency_days: list[int] = Field(default_factory=list)
    seats_per_occurrence: int = Field(default=0, ge=0)

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str | None):
        if v is not None and v not in AVAILABILITY_FREQUENCIES:
            raise ValueError(f"frequency must be one of {AVAILABILITY_FREQUENCIES}")
        return v

    @field_validator("frequency_days")
    @classmethod
    def validate_frequency_days(cls, v: list[int]):
        if any(day < 0 or day > 6 for day in v):
            raise ValueError("frequency_days must contain weekday values 0 (Monday) through 6 (Sunday)")
        return v

    @model_validator(mode="after")
    def validate_range_and_frequency(self) -> "AvailabilityConfigPayload":
        if self.availability_start_date and self.availability_end_date and self.availability_end_date < self.availability_start_date:
            raise ValueError("availability_end_date must be on or after availability_start_date")
        if self.frequency and not self.frequency_days:
            raise ValueError("Select at least one day of the week for the chosen frequency")
        if self.frequency in ("fortnightly",) and self.frequency_week not in (1, 2):
            raise ValueError("frequency_week must be 1 or 2 for a fortnightly schedule")
        if self.frequency == "monthly" and self.frequency_week not in (1, 2, 3, 4):
            raise ValueError("frequency_week must be between 1 and 4 for a monthly schedule")
        return self


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
