"""External (affiliate-redirect) inventory: provider config, destination
mapping and outbound click analytics.

Deliberately separate from the tours/bookings models - external products are
never stored as Tourvaa tours, and a click is an analytics event, not a
booking. See app/integrations/external_tours.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ExternalProvider(Base):
    """Non-secret per-provider settings and status. Credentials are NOT here:
    they stay encrypted in api_settings (admin) / .env (fallback), and the
    master on/off switch is api_settings.is_enabled + VIATOR_ENABLED."""
    __tablename__ = "external_providers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), unique=True, nullable=False, index=True)  # VIATOR
    name = Column(String(100), nullable=False)
    public_category = Column(String(120), default="Day Tours & Experiences", nullable=False)
    show_on_homepage = Column(Boolean, default=True, nullable=False)
    show_on_destination_pages = Column(Boolean, default=True, nullable=False)
    show_on_itinerary = Column(Boolean, default=True, nullable=False)
    show_in_search = Column(Boolean, default=True, nullable=False)
    last_connection_status = Column(String(20), nullable=True)  # connected | error
    last_connection_message = Column(String(255), nullable=True)
    last_connection_at = Column(DateTime(timezone=True), nullable=True)
    last_destination_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_destination_sync_status = Column(String(20), nullable=True)
    last_destination_sync_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExternalDestinationMapping(Base):
    """One row per provider destination (synced from the provider), with an
    optional link to Tourvaa's own country/state/city. Tourvaa destination
    ids are never replaced by provider ids - this table only maps between
    them."""
    __tablename__ = "external_destination_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "provider_destination_id", name="uq_ext_dest_provider_id"),
        UniqueConstraint("provider", "slug", name="uq_ext_dest_provider_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(40), nullable=False, index=True)
    provider_destination_id = Column(String(40), nullable=False)
    provider_destination_name = Column(String(255), nullable=False)
    provider_destination_type = Column(String(40), nullable=True)  # CITY, COUNTRY, REGION ...
    provider_parent_destination_id = Column(String(40), nullable=True, index=True)
    provider_default_currency = Column(String(3), nullable=True)
    # The provider's own affiliate link for this destination (Viator's
    # destinationUrl, already carrying pid/mcid) - used as-is for hand-offs.
    provider_destination_url = Column(Text, nullable=True)
    # SEO route segment for /day-tours/<slug> - unique per provider.
    slug = Column(String(191), nullable=False)
    tourvaa_country_id = Column(Integer, ForeignKey("countries.id", ondelete="SET NULL"), nullable=True, index=True)
    tourvaa_state_id = Column(Integer, ForeignKey("states.id", ondelete="SET NULL"), nullable=True, index=True)
    tourvaa_city_id = Column(Integer, ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True)
    # "auto" = matched by name during sync (re-matched on every sync);
    # "manual" = set by an admin (never overwritten by sync).
    mapping_source = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    country = relationship("Country")
    state = relationship("State")
    city = relationship("City")


class ExternalAffiliateClick(Base):
    """Outbound click to a provider's affiliate URL. Analytics only - NOT a
    booking: no capacity, invoice, payment, supplier payout or agent
    commission is ever derived from these rows."""
    __tablename__ = "external_affiliate_clicks"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(40), nullable=False, index=True)
    product_code = Column(String(80), nullable=False, index=True)
    product_title = Column(String(255), nullable=True)
    provider_destination_id = Column(String(40), nullable=True, index=True)
    tourvaa_country_id = Column(Integer, ForeignKey("countries.id", ondelete="SET NULL"), nullable=True)
    tourvaa_city_id = Column(Integer, ForeignKey("cities.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    campaign = Column(String(80), nullable=True, index=True)
    source_page = Column(String(40), nullable=True, index=True)
    page_path = Column(String(255), nullable=True)
    external_url = Column(Text, nullable=True)
    external_url_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
