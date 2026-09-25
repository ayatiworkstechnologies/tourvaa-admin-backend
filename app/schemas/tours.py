from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

PHYSICAL_RATINGS = {"easy", "moderate", "hard"}
ITEM_STATUSES = {"active", "inactive"}
IMAGE_TYPES = {"gallery", "itinerary", "highlight", "banner", "map"}
CALENDAR_STATUSES = {"available", "unavailable", "sold_out", "blocked"}
AVAILABILITY_FREQUENCIES = {"weekly", "fortnightly", "monthly"}
DISCOUNT_TYPES = {"percentage", "fixed"}
DISCOUNT_SCOPES = {"tour", "all_tours", "category", "country"}
PRICE_TYPES = {"per_person", "per_booking", "per_room", "per_person_per_night", "per_room_per_night"}


def _reject_ambiguous_commission_mode(commissionable: bool, supplier_cost) -> None:
    """supplier_cost (cost-plus) and commissionable=False (percentage-model
    opt-out) are two different ways of saying "don't apply Tourvaa's
    commission % to this item's customer price" -- see
    services.bookings.compute_booking_supplier_financials, where supplier_cost
    silently wins over commissionable when both are set. Reject the
    combination outright instead of silently ignoring commissionable, so an
    admin who sets both gets a clear error rather than a config that doesn't
    do what its own commissionable=False flag implies."""
    if supplier_cost is not None and commissionable is False:
        raise ValueError(
            "commissionable=false has no effect when supplier_cost is set (cost-plus already excludes this item "
            "from commission) -- set commissionable=true (or omit it) when using supplier_cost, or clear "
            "supplier_cost if you only want the commissionable flag."
        )
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
    # "standard" or "free_day" (explicit flag for free/leisure days; see
    # TourItinerary.day_type). Optional so existing clients are unaffected.
    day_type: str = Field(default="standard", max_length=20)

    @field_validator("day_type", mode="before")
    @classmethod
    def validate_day_type(cls, v):
        return v if v in ("standard", "free_day") else "standard"

    @model_validator(mode="before")
    @classmethod
    def coerce_null_text_fields(cls, data):
        # Several TourItinerary DB columns are nullable Text/String with no
        # DB-level default enforcement (see app.models.tours.TourItinerary),
        # so existing rows can hold NULL - and the frontend round-trips GET
        # data straight back into this POST/PUT payload (see
        # TourItineraryTab.tsx's `save`), so a None here from an old row is
        # expected, not client error. Treat it the same as "" rather than
        # 422ing (mirrors TourOverviewPayload.coerce_null_text_fields).
        if isinstance(data, dict):
            for key in (
                "short_description", "long_description", "activities",
                "optional_activities", "accommodation", "start_time", "end_time",
                "travel_distance", "travel_duration", "transport_type",
                "meals_included", "important_notes",
            ):
                if data.get(key) is None:
                    data[key] = ""
        return data

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
    price_type: str = Field(default="per_booking", max_length=20)
    category: str = Field(default="other", max_length=30)
    display_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", max_length=20)
    # When False, this extension's price is excluded from Tourvaa's
    # commission base (paid to the supplier in full) -- see
    # services.bookings.compute_booking_supplier_financials.
    commissionable: bool = True
    # Cost-plus margin: when set, the supplier is paid this exact per-unit
    # cost (no commission %) and Tourvaa's margin is customer price minus
    # this -- mutually exclusive with the commissionable flag above (see
    # models.tours.TourExtension.supplier_cost). None means unset/legacy.
    supplier_cost: Optional[Decimal] = None

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

    @model_validator(mode="after")
    def validate_commission_mode(self):
        _reject_ambiguous_commission_mode(self.commissionable, self.supplier_cost)
        return self

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
    # adult_price/child_price are the public customer prices. Tourvaa's
    # floor-enforced commission is deducted from them to produce the
    # supplier_final_* settlement amounts.
    adult_price: float = Field(ge=0)
    child_price: float = Field(default=0.0, ge=0)
    # This slab's own commission rate. Floor-enforced server-side against
    # resolve_effective_commission_percentage (Tour > Supplier > platform
    # minimum) - a supplier may raise it, never lower it. None means "use
    # that resolved floor directly".
    commission_percentage: float | None = Field(default=None, ge=0, le=100)
    # supplier_price/final_price are legacy/unused, kept for backward
    # compatibility only - no longer applied to pricing.
    supplier_price: float = Field(default=0.0, ge=0)
    final_price: float = Field(default=0.0, ge=0)
    # Admin-only markup percentage. The service ignores supplier-provided
    # values and preserves/defaults the server-controlled markup instead.
    admin_markup_value: float = Field(default=0.0, ge=0, le=100)
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


# per-date seasonal/peak price override (admin only) - see models.tours.TourDatePrice
class DatePricePayload(BaseModel):
    price_date: date
    adult_price: float = Field(ge=0)
    child_price: float = Field(default=0.0, ge=0)
    status: str = Field(default="active", max_length=20)
    # Required when an admin (not the tour's supplier) creates or changes a
    # date price: under the commission-deduction model the date price is
    # the supplier's selling price, so overriding it changes the supplier's
    # payout. Recorded in the audit log and sent to the supplier. Not stored
    # on the row.
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def validate_date_price_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v


# optional activity
ACTIVITY_PRICING_MODES = {"flat", "per_passenger_type"}


class OptionalActivityPayload(BaseModel):
    activity_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    price_per_person: float = Field(default=0.0, ge=0)
    # Only read when pricing_mode == "per_passenger_type". None means "same
    # as price_per_person" for child_price, and "free" (0) for infant_price
    # -- an infant price left unset is a deliberate choice here, unlike the
    # Tour.infant_price column bug (ID 01), because this field only exists
    # once an admin has opted into per-passenger-type pricing at all.
    child_price_per_person: float | None = Field(default=None, ge=0)
    infant_price_per_person: float | None = Field(default=None, ge=0)
    pricing_mode: str = Field(default="flat", max_length=20)
    image: str = Field(default="", max_length=255)
    category: str = Field(default="other", max_length=30)
    status: str = Field(default="active", max_length=20)
    # When False, this activity's price is excluded from Tourvaa's
    # commission base (paid to the supplier in full) -- see
    # services.bookings.compute_booking_supplier_financials.
    commissionable: bool = True
    # See ExtensionPayload.supplier_cost above.
    supplier_cost: Optional[Decimal] = None

    @field_validator("pricing_mode")
    @classmethod
    def validate_pricing_mode(cls, v: str):
        if v not in ACTIVITY_PRICING_MODES:
            raise ValueError(f"pricing_mode must be one of {ACTIVITY_PRICING_MODES}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str):
        if v not in ADDON_CATEGORIES:
            raise ValueError(f"category must be one of {ADDON_CATEGORIES}")
        return v

    @model_validator(mode="after")
    def validate_commission_mode(self):
        _reject_ambiguous_commission_mode(self.commissionable, self.supplier_cost)
        return self

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
    # When False, this accommodation extra's price is excluded from
    # Tourvaa's commission base (paid to the supplier in full) -- see
    # services.bookings.compute_booking_supplier_financials.
    commissionable: bool = True
    # See ExtensionPayload.supplier_cost above.
    supplier_cost: Optional[Decimal] = None

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

    @model_validator(mode="after")
    def validate_commission_mode(self):
        _reject_ambiguous_commission_mode(self.commissionable, self.supplier_cost)
        return self

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
    agent_no_deposit_buffer_weeks: int = Field(default=4, ge=0)
    agent_reserve_deposit_percentage: float = Field(default=30.0, ge=0, le=100)
    frequency: str | None = None
    frequency_week: int | None = Field(default=None, ge=1, le=4)
    # Monthly only: 1-4 = 1st-4th occurrence of each chosen weekday, 5 = the last one.
    frequency_weeks: list[int] = Field(default_factory=list)
    frequency_days: list[int] = Field(default_factory=list)
    seats_per_occurrence: int = Field(default=0, ge=0)
    # When the schedule changes, also delete unbooked calendar dates that no longer fit it.
    remove_unmatched_dates: bool = False

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

    @field_validator("frequency_weeks")
    @classmethod
    def validate_frequency_weeks(cls, v: list[int]):
        if any(week < 1 or week > 5 for week in v):
            raise ValueError("frequency_weeks must contain 1-4 (1st-4th) or 5 (last)")
        return sorted(set(v))

    @model_validator(mode="after")
    def validate_range_and_frequency(self) -> "AvailabilityConfigPayload":
        if self.availability_start_date and self.availability_end_date and self.availability_end_date < self.availability_start_date:
            raise ValueError("availability_end_date must be on or after availability_start_date")
        if self.frequency and not self.frequency_days:
            raise ValueError("Select at least one day of the week for the chosen frequency")
        if self.frequency in ("fortnightly",) and self.frequency_week not in (1, 2):
            raise ValueError("frequency_week must be 1 or 2 for a fortnightly schedule")
        if self.frequency == "monthly":
            if not self.frequency_weeks and self.frequency_week in (1, 2, 3, 4):
                self.frequency_weeks = [self.frequency_week]  # older clients send a single week
            if not self.frequency_weeks:
                raise ValueError("Select at least one week of the month for a monthly schedule")
            self.frequency_week = self.frequency_weeks[0] if self.frequency_weeks[0] <= 4 else None
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
    # Who absorbs this promo code's discount amount -- "SUPPLIER" (default,
    # unchanged legacy behavior) or "TOURVAA" (Tourvaa's own margin absorbs
    # it instead; see services.bookings.compute_booking_supplier_financials).
    funded_by: str = Field(default="SUPPLIER", max_length=20)
    # Promo codes only: list the code on the tour page/checkout for one-click
    # apply (True), or keep it private so it only works when typed (False).
    show_on_website: bool = True

    @field_validator("discount_type")
    @classmethod
    def validate_type(cls, v: str):
        if v not in DISCOUNT_TYPES:
            raise ValueError(f"discount_type must be one of {DISCOUNT_TYPES}")
        return v

    @field_validator("funded_by")
    @classmethod
    def validate_funded_by(cls, v: str):
        v = (v or "SUPPLIER").upper()
        if v not in {"SUPPLIER", "TOURVAA", "SHARED"}:
            raise ValueError("funded_by must be one of ['SUPPLIER', 'TOURVAA', 'SHARED']")
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


class DiscountAmendment(BaseModel):
    """Replaces free-form editing of a discount: a supplier/admin may only
    extend the validity window and/or change the percentage/value, and each
    amendment is recorded as a new TourDiscountHistory version rather than
    silently overwriting the original record."""

    new_discount_value: float | None = Field(default=None, ge=0)
    new_end_date: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_a_change(self) -> "DiscountAmendment":
        if self.new_discount_value is None and self.new_end_date is None:
            raise ValueError("Provide a new percentage/value and/or a new (later) end date")
        return self


class DiscountDeactivateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# group-size discount tier, scoped to the whole Tour (not a pricing slab) -
# see models.tours.TourGroupDiscountTier for why this is a separate concept
# from DiscountPayload (promo codes).
class GroupDiscountTierPayload(BaseModel):
    min_pax: int = Field(ge=1)
    max_pax: int = Field(ge=1)
    discount_type: str = Field(max_length=20)
    discount_value: float = Field(ge=0)
    status: str = Field(default="active", max_length=20)
    # Who absorbs this group discount -- "SUPPLIER" (default, unchanged
    # legacy behavior: the discount ratio also reduces the supplier's own
    # net_earnings) or "TOURVAA" (supplier is paid as if the discount never
    # happened; see services.bookings.compute_booking_supplier_financials).
    funded_by: str = Field(default="SUPPLIER", max_length=20)

    @field_validator("discount_type")
    @classmethod
    def validate_type(cls, v: str):
        if v not in DISCOUNT_TYPES:
            raise ValueError(f"discount_type must be one of {DISCOUNT_TYPES}")
        return v

    @field_validator("funded_by")
    @classmethod
    def validate_funded_by(cls, v: str):
        v = (v or "SUPPLIER").upper()
        if v not in {"SUPPLIER", "TOURVAA", "SHARED"}:
            raise ValueError("funded_by must be one of ['SUPPLIER', 'TOURVAA', 'SHARED']")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        if v not in ITEM_STATUSES:
            raise ValueError("Invalid status")
        return v

    @model_validator(mode="after")
    def validate_range_and_bound(self) -> "GroupDiscountTierPayload":
        if self.max_pax < self.min_pax:
            raise ValueError("max_pax must be greater than or equal to min_pax")
        if self.discount_type == "percentage" and self.discount_value > 100:
            raise ValueError("A percentage discount_value cannot exceed 100")
        return self


# price calculation
class PriceCalculationRequest(BaseModel):
    tour_date: datetime | None = None
    adults_count: int = Field(default=1, ge=1)
    children_count: int = Field(default=0, ge=0)
    optional_activity_ids: list[int] = Field(default_factory=list)
    accommodation_extra_ids: list[int] = Field(default_factory=list)
    tour_extension_ids: list[int] = Field(default_factory=list)
    promo_code: str | None = None
    # Optional, forward-compatible with services.bookings._price_booking
    # (the same calculator this preview now delegates to) -- needed to
    # quote a per_person_per_night/per_room_per_night extension or
    # accommodation extra correctly. Omitting them just means those specific
    # priced-per-night items can't be quoted (an explicit 400, not a silent
    # wrong number as the old standalone calculator used to give).
    tour_end_date: datetime | None = None
    no_of_rooms: int | None = Field(default=None, ge=1)
    no_of_infants: int = Field(default=0, ge=0)
