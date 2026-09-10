from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class HomepageBanner(Base):
    __tablename__ = "cms_homepage_banners"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    subtitle = Column(String(400), nullable=True)
    # Nullable: a banner needs at least one of image/video (enforced in
    # BannerPayload), not both - image also doubles as the <video> poster
    # frame and the fallback for browsers/crawlers that don't render video,
    # when both are set.
    image = Column(String(255), nullable=True)
    video = Column(String(255), nullable=True)
    cta_text = Column(String(100), nullable=True)
    cta_url = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PopularDestination(Base):
    __tablename__ = "cms_popular_destinations"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    image = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PopularTour(Base):
    __tablename__ = "cms_popular_tours"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HandpickedTour(Base):
    """Backs the homepage's 'Handpicked Tours for You' carousel - a
    separate curated list from PopularTour ('Trending Tour Packages') so an
    admin can pin different tours to each section instead of the two
    sections silently mirroring each other."""
    __tablename__ = "cms_handpicked_tours"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FavouriteCountryEntry(Base):
    """Backs the homepage's 'Favourite Countries for Travellers' editorial
    list - distinct from PopularDestination (the 'Countries Worth
    Exploring' carousel, which is generated from real tour counts): this
    one is a hand-picked list with its own custom snippet copy per
    country."""
    __tablename__ = "cms_favourite_countries"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    snippet = Column(Text, nullable=True)
    image = Column(String(255), nullable=True)
    href = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class HomepageContentBlock(Base):
    """Generic key/JSON-value store for one-off homepage content blocks that
    don't need their own table (hero trust badge + offer strip, the About
    Tourvaa section, the blog teaser banner, the airport-transfers banner).
    One row per `key`; `data` shape is whatever that block's admin form and
    the homepage renderer agree on - see ALLOWED_CONTENT_BLOCK_KEYS in
    app/services/website_cms.py for the recognised keys."""
    __tablename__ = "cms_homepage_content_blocks"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(60), unique=True, nullable=False, index=True)
    data = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TourOnDeal(Base):
    __tablename__ = "cms_tours_on_deals"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    deal_label = Column(String(100), nullable=True)
    discount_percentage = Column(Integer, default=0, nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Blog(Base):
    __tablename__ = "cms_blogs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, nullable=False, index=True)
    excerpt = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    featured_image = Column(String(255), nullable=True)
    author = Column(String(120), nullable=True)
    tags = Column(JSON, nullable=True)
    seo_title = Column(String(200), nullable=True)
    seo_description = Column(String(400), nullable=True)
    status = Column(String(20), default="draft", nullable=False)
    # draft, published
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustomerReview(Base):
    __tablename__ = "cms_customer_reviews"

    id = Column(Integer, primary_key=True, index=True)
    reviewer_name = Column(String(120), nullable=False)
    reviewer_image = Column(String(255), nullable=True)
    rating = Column(Integer, default=5, nullable=False)
    review_text = Column(Text, nullable=False)
    tour_name = Column(String(200), nullable=True)
    country = Column(String(100), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class HelpCentreArticle(Base):
    __tablename__ = "cms_help_centre"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CmsPage(Base):
    """Admin-authored pages created dynamically (not the small fixed set of
    legal documents CmsPolicy covers) - title/content/SEO, an enable/disable
    status, and an optional footer section assignment so a published page
    can automatically appear as a footer link (see get_public_footer)."""
    __tablename__ = "cms_pages"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, nullable=False, index=True)
    content = Column(Text, nullable=True)
    seo_title = Column(String(200), nullable=True)
    seo_description = Column(String(400), nullable=True)
    status = Column(String(20), default="draft", nullable=False)
    # draft, published - "published" is what makes a page reachable at its
    # slug URL and eligible to appear in its assigned footer section.
    footer_section_id = Column(Integer, ForeignKey("cms_footer_sections.id"), nullable=True, index=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CmsPolicy(Base):
    """Stores Terms & Conditions, Cookie Policy, Cancellation Policy, etc."""
    __tablename__ = "cms_policies"

    id = Column(Integer, primary_key=True, index=True)
    # slug: terms-conditions, cookie-policy, cancellation-policy, privacy-policy
    slug = Column(String(80), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    last_updated = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PromotionalPopup(Base):
    __tablename__ = "cms_promotional_popups"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    image = Column(String(255), nullable=True)
    cta_text = Column(String(100), nullable=True)
    cta_url = Column(String(500), nullable=True)
    display_after_seconds = Column(Integer, default=3, nullable=False)
    display_frequency = Column(String(20), default="once", nullable=False)
    # once, session, always
    is_active = Column(Boolean, default=False, nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExternalLink(Base):
    __tablename__ = "cms_external_links"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(120), nullable=False)
    url = Column(String(500), nullable=False)
    open_in_new_tab = Column(Boolean, default=True, nullable=False)
    location = Column(String(50), default="footer", nullable=False)
    # header, footer, sidebar, nav
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FooterSection(Base):
    __tablename__ = "cms_footer_sections"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(120), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    links = relationship("FooterLink", back_populates="section", cascade="all, delete-orphan", order_by="FooterLink.sort_order")


class FooterLink(Base):
    __tablename__ = "cms_footer_links"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("cms_footer_sections.id"), nullable=False, index=True)
    label = Column(String(120), nullable=False)
    url = Column(String(500), nullable=False)
    open_in_new_tab = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    section = relationship("FooterSection", back_populates="links")


class SitemapEntry(Base):
    __tablename__ = "cms_sitemap_entries"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(500), nullable=False)
    change_frequency = Column(String(20), default="weekly", nullable=False)
    priority = Column(String(5), default="0.5", nullable=False)
    last_modified = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
