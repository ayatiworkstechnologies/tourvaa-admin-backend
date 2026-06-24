from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


class HomepageBanner(Base):
    __tablename__ = "cms_homepage_banners"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    subtitle = Column(String(400), nullable=True)
    image = Column(String(255), nullable=False)
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
