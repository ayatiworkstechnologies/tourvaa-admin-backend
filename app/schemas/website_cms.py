from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class BannerPayload(BaseModel):
    title: str
    subtitle: Optional[str] = None
    image: Optional[str] = None
    video: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _require_image_or_video(self) -> "BannerPayload":
        if not (self.image or "").strip() and not (self.video or "").strip():
            raise ValueError("Upload an image or a video for the banner")
        return self


class PopularDestinationPayload(BaseModel):
    country_id: Optional[int] = None
    city_id: Optional[int] = None
    title: str
    image: Optional[str] = None
    description: Optional[str] = None
    href: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    package_count: Optional[int] = Field(default=None, ge=0)
    sort_order: int = 0
    is_active: bool = True


class PopularTourPayload(BaseModel):
    tour_id: int
    sort_order: int = 0
    is_active: bool = True


class TourOnDealPayload(BaseModel):
    tour_id: int
    deal_label: Optional[str] = None
    discount_percentage: int = 0
    valid_until: Optional[datetime] = None
    sort_order: int = 0
    is_active: bool = True


class HandpickedTourPayload(BaseModel):
    tour_id: int
    sort_order: int = 0
    is_active: bool = True


class FavouriteCountryPayload(BaseModel):
    country_id: Optional[int] = None
    title: str
    snippet: Optional[str] = None
    image: Optional[str] = None
    href: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class CountryPagePayload(BaseModel):
    country_id: int
    # Keep request validation aligned with the persisted CountryPage columns.
    # Without these limits, PostgreSQL rejects an otherwise valid request and
    # the admin UI receives an avoidable 500 response.
    hero_title: Optional[str] = Field(default=None, max_length=200)
    hero_description: Optional[str] = None
    hero_image: Optional[str] = Field(default=None, max_length=255)
    showcase_title: Optional[str] = Field(default=None, max_length=200)
    showcase_description: Optional[str] = None
    showcase_image: Optional[str] = Field(default=None, max_length=255)
    seo_title: Optional[str] = Field(default=None, max_length=200)
    seo_description: Optional[str] = Field(default=None, max_length=400)
    is_active: bool = True


class ContentBlockPayload(BaseModel):
    data: Dict[str, Any] = {}


class BlogPayload(BaseModel):
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    featured_image: Optional[str] = None
    banner_title: Optional[str] = None
    banner_alt: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    status: str = "draft"


class CmsPagePayload(BaseModel):
    title: str
    slug: Optional[str] = None
    content: Optional[str] = None
    sections: Optional[List[Dict[str, Any]]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    status: str = "draft"
    footer_section_id: Optional[int] = None
    sort_order: int = 0


class ReviewPayload(BaseModel):
    reviewer_name: str
    reviewer_image: Optional[str] = None
    rating: int = 5
    review_text: str
    tour_name: Optional[str] = None
    country: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class HelpArticlePayload(BaseModel):
    category: str
    question: str
    answer: str
    sort_order: int = 0
    is_active: bool = True


class PolicyPayload(BaseModel):
    slug: str
    title: str
    content: str


class PopupPayload(BaseModel):
    title: str
    content: Optional[str] = None
    image: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    display_after_seconds: int = 3
    display_frequency: str = "once"
    is_active: bool = False
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class ExternalLinkPayload(BaseModel):
    label: str
    url: str
    open_in_new_tab: bool = True
    location: str = "footer"
    sort_order: int = 0
    is_active: bool = True


class FooterSectionPayload(BaseModel):
    title: str
    sort_order: int = 0
    is_active: bool = True


class FooterLinkPayload(BaseModel):
    section_id: int
    label: str
    url: str
    open_in_new_tab: bool = False
    sort_order: int = 0
    is_active: bool = True


class SitemapEntryPayload(BaseModel):
    url: str
    change_frequency: str = "weekly"
    priority: str = "0.5"
    is_active: bool = True
