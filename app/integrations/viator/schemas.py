"""Request/response models for the external-tours API (Viator today).

The browser only ever sends these validated Tourvaa-shaped fields; the Viator
request body is always built server-side (see service.build_search_payload).
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.integrations.external_tours.constants import CAMPAIGN_SOURCES

# Currencies the Viator Partner API accepts for pricing.
SUPPORTED_CURRENCIES = (
    "USD", "EUR", "GBP", "AUD", "CAD", "NZD", "INR", "SGD", "HKD", "JPY",
    "CHF", "DKK", "NOK", "SEK", "ZAR", "BRL", "TWD",
)

SortOption = Literal["recommended", "rating", "price_asc", "price_desc", "duration", "newest"]


class ExternalTourSearchRequest(BaseModel):
    provider: str = Field(default="VIATOR", max_length=20)
    # Either a /day-tours slug ("dubai"), a provider destination id ("828"),
    # or a free location name + optional country (resolved via the mapping
    # table - used by tour itineraries).
    destination: Optional[str] = Field(default=None, max_length=191)
    location: Optional[str] = Field(default=None, max_length=191)
    country: Optional[str] = Field(default=None, max_length=120)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    category: Optional[int] = Field(default=None, ge=1)
    min_price: Optional[float] = Field(default=None, ge=0, le=100000)
    max_price: Optional[float] = Field(default=None, ge=0, le=100000)
    min_rating: Optional[float] = Field(default=None, ge=0, le=5)
    free_cancellation: bool = False
    sort: SortOption = "recommended"
    page: int = Field(default=1, ge=1, le=200)
    page_size: int = Field(default=12, ge=1, le=24)
    currency: str = Field(default="USD", max_length=3)
    source: str = Field(default="day-tours", max_length=30)

    @field_validator("provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        v = (v or "VIATOR").upper()
        if v != "VIATOR":
            raise ValueError("Unsupported provider")
        return v

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        v = (v or "USD").upper()
        return v if v in SUPPORTED_CURRENCIES else "USD"

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        return v if v in CAMPAIGN_SOURCES else "day-tours"

    @model_validator(mode="after")
    def _ranges(self):
        if not (self.destination or self.location or self.country):
            raise ValueError("A destination is required")
        if self.start_date and self.start_date < date.today():
            self.start_date = date.today()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.end_date and not self.start_date:
            self.start_date = date.today()
        if self.min_price is not None and self.max_price is not None and self.max_price < self.min_price:
            raise ValueError("max_price must be greater than min_price")
        return self


class ExternalClickRequest(BaseModel):
    provider: str = Field(default="VIATOR", max_length=20)
    product_code: str = Field(min_length=1, max_length=80)
    product_title: Optional[str] = Field(default=None, max_length=255)
    provider_destination_id: Optional[str] = Field(default=None, max_length=40)
    external_url: str = Field(min_length=10, max_length=2000)
    source_page: str = Field(default="day-tours", max_length=30)
    page_path: Optional[str] = Field(default=None, max_length=255)
    session_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        return (v or "VIATOR").upper()

    @field_validator("source_page")
    @classmethod
    def _source(cls, v: str) -> str:
        return v if v in CAMPAIGN_SOURCES else "day-tours"

    @field_validator("product_code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip()
        if not all(ch.isalnum() or ch in "-_" for ch in v):
            raise ValueError("Invalid product code")
        return v


class ExternalRedirectRequest(BaseModel):
    """Destination-level hand-off to the provider's site (no product)."""
    destination: Optional[str] = Field(default=None, max_length=191)
    country: Optional[str] = Field(default=None, max_length=120)
    source: str = Field(default="home", max_length=30)
    page_path: Optional[str] = Field(default=None, max_length=255)
    session_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        return v if v in CAMPAIGN_SOURCES else "home"


class ProviderSettingsUpdate(BaseModel):
    show_on_homepage: Optional[bool] = None
    show_on_destination_pages: Optional[bool] = None
    show_on_itinerary: Optional[bool] = None
    show_in_search: Optional[bool] = None


class DestinationMappingUpdate(BaseModel):
    tourvaa_country_id: Optional[int] = Field(default=None, ge=1)
    tourvaa_state_id: Optional[int] = Field(default=None, ge=1)
    tourvaa_city_id: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None
    # true = clear the Tourvaa link and let the next sync auto-match again
    reset_to_auto: bool = False
