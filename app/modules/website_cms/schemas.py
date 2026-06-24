from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class BannerPayload(BaseModel):
    title: str
    subtitle: Optional[str] = None
    image: str
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class PopularDestinationPayload(BaseModel):
    country_id: Optional[int] = None
    city_id: Optional[int] = None
    title: str
    image: Optional[str] = None
    description: Optional[str] = None
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


class BlogPayload(BaseModel):
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    featured_image: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    status: str = "draft"


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


class SitemapEntryPayload(BaseModel):
    url: str
    change_frequency: str = "weekly"
    priority: str = "0.5"
    is_active: bool = True
