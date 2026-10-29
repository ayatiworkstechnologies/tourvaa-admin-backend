from datetime import datetime
from math import isfinite
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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
    # Content blocks are intentionally flexible, but they must remain bounded
    # JSON documents.  The individual editor owns its field-level UX rules.
    data: Dict[str, Any] = Field(default_factory=dict, max_length=100)
    expected_version: Optional[int] = Field(default=None, ge=0)

    @field_validator("data")
    @classmethod
    def validate_json_document(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        def visit(item: Any, depth: int = 0) -> None:
            if depth > 8:
                raise ValueError("CMS content cannot be nested more than 8 levels")
            if item is None or isinstance(item, (str, bool, int)):
                return
            if isinstance(item, float):
                if not isfinite(item):
                    raise ValueError("CMS content cannot contain non-finite numbers")
                return
            if isinstance(item, list):
                if len(item) > 100:
                    raise ValueError("CMS content lists accept at most 100 items")
                for child in item:
                    visit(child, depth + 1)
                return
            if isinstance(item, dict):
                if len(item) > 100:
                    raise ValueError("CMS content objects accept at most 100 fields")
                if any(not isinstance(key, str) for key in item):
                    raise ValueError("CMS content object keys must be strings")
                for child in item.values():
                    visit(child, depth + 1)
                return
            raise ValueError("CMS content must contain JSON-compatible values only")

        visit(value)
        return value


class BlogFaqPayload(BaseModel):
    # The editor accepts any non-empty plain-text question.  Keep the API
    # contract identical so legacy FAQs such as "Hi" can be recovered and
    # saved instead of blocking the whole article with a 422.
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=2000)

    @field_validator("question", "answer", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class BlogPayload(BaseModel):
    """The editorial contract shared by the admin studio and public blog.

    Keep topic taxonomy as a simple JSON list for now: it is portable across
    deployments while the API normalises it into stable, searchable values.
    """
    title: str = Field(min_length=3, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=220)
    excerpt: Optional[str] = Field(default=None, max_length=600)
    content: Optional[str] = None
    featured_image: Optional[str] = Field(default=None, max_length=255)
    banner_title: Optional[str] = Field(default=None, max_length=200)
    banner_alt: Optional[str] = Field(default=None, max_length=300)
    author: Optional[str] = Field(default=None, max_length=120)
    tags: Optional[List[str]] = Field(default=None, max_length=12)
    faqs: Optional[List[BlogFaqPayload]] = Field(default=None, max_length=30)
    seo_title: Optional[str] = Field(default=None, max_length=200)
    seo_description: Optional[str] = Field(default=None, max_length=400)
    status: Literal["draft", "published", "scheduled"] = "draft"
    scheduled_at: Optional[datetime] = None
    category: Optional[str] = Field(default=None, max_length=120)
    og_image: Optional[str] = Field(default=None, max_length=255)
    related_tour_ids: Optional[List[int]] = None

    @field_validator("scheduled_at", mode="before")
    @classmethod
    def normalise_blank_schedule(cls, value):
        # Older admin clients may submit an empty datetime-local field. Treat
        # that as no schedule instead of returning an unhelpful 422 error.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def require_schedule_for_scheduled_post(self) -> "BlogPayload":
        # A scheduled post with no timestamp never becomes public. Enforce
        # this at the API boundary as well as in the editor so older or direct
        # API clients cannot create an inert scheduled article.
        if self.status == "scheduled" and self.scheduled_at is None:
            raise ValueError("Scheduled posts require a publish date and time")
        return self

    @field_validator("title", "slug", "excerpt", "featured_image", "banner_title", "banner_alt", "author", "seo_title", "seo_description", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("tags")
    @classmethod
    def normalise_tags(cls, tags: Optional[List[str]]) -> Optional[List[str]]:
        if tags is None:
            return None
        cleaned: list[str] = []
        for tag in tags:
            value = tag.strip()
            if not value:
                continue
            if len(value) > 60:
                raise ValueError("Each topic must be 60 characters or fewer")
            if value.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(value)
        return cleaned


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
    rating: float = Field(default=5, ge=1, le=5, multiple_of=0.5)
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
