from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class TourOverview(Base):
    __tablename__ = "tour_overviews"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, unique=True, index=True)
    duration_text = Column(String(100), default="", nullable=False)
    start_location = Column(String(150), default="", nullable=False)
    end_location = Column(String(150), default="", nullable=False)
    group_size = Column(String(100), default="", nullable=False)
    tour_type = Column(String(100), default="", nullable=False)
    physical_rating = Column(String(20), default="easy", nullable=False)
    overview_icon_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourItinerary(Base):
    __tablename__ = "tour_itineraries"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    day_number = Column(Integer, nullable=False)
    day_title = Column(String(255), default="", nullable=False)
    location_name = Column(String(255), default="", nullable=False)
    short_description = Column(Text, default="", nullable=True)
    long_description = Column(Text, default="", nullable=True)
    activities = Column(Text, default="", nullable=True)
    image = Column(String(255), default="", nullable=False)
    image_alt_text = Column(String(180), default="", nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourInclusion(Base):
    __tablename__ = "tour_inclusions"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    icon = Column(String(255), default="", nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="", nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourExclusion(Base):
    __tablename__ = "tour_exclusions"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    icon = Column(String(255), default="", nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="", nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourHighlight(Base):
    __tablename__ = "tour_highlights"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    image = Column(String(255), default="", nullable=False)
    title = Column(String(255), nullable=False)
    short_description = Column(Text, default="", nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourSimilar(Base):
    __tablename__ = "tour_similar_tours"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    similar_tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("tour_id", "similar_tour_id", name="uq_tour_similar"),)

    tour = relationship("Tour", foreign_keys=[tour_id])
    similar_tour = relationship("Tour", foreign_keys=[similar_tour_id])


class TourExtension(Base):
    __tablename__ = "tour_extensions"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    extension_tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    extension_title = Column(String(255), default="", nullable=False)
    extension_note = Column(Text, default="", nullable=True)
    extra_price = Column(Float, default=0.0, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour", foreign_keys=[tour_id])
    extension_tour = relationship("Tour", foreign_keys=[extension_tour_id])


class TourGalleryImage(Base):
    __tablename__ = "tour_gallery_images"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    image_path = Column(String(255), nullable=False)
    image_title = Column(String(255), default="", nullable=False)
    image_alt_text = Column(String(180), default="", nullable=False)
    image_caption = Column(Text, default="", nullable=True)
    image_type = Column(String(30), default="gallery", nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


# ── Week 10 ──────────────────────────────────────────────────────────────────

class TourPricing(Base):
    __tablename__ = "tour_pricing"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    passenger_from = Column(Integer, nullable=False)
    passenger_to = Column(Integer, nullable=False)
    adult_price = Column(Float, nullable=False)
    child_price = Column(Float, default=0.0, nullable=False)
    supplier_price = Column(Float, default=0.0, nullable=False)
    markup_type = Column(String(20), default="percentage", nullable=False)
    markup_value = Column(Float, default=0.0, nullable=False)
    final_price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourOptionalActivity(Base):
    __tablename__ = "tour_optional_activities"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    activity_name = Column(String(255), nullable=False)
    description = Column(Text, default="", nullable=True)
    price_per_person = Column(Float, default=0.0, nullable=False)
    image = Column(String(255), default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourAccommodationExtra(Base):
    __tablename__ = "tour_accommodation_extras"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    accommodation_name = Column(String(255), nullable=False)
    description = Column(Text, default="", nullable=True)
    extra_price = Column(Float, default=0.0, nullable=False)
    price_type = Column(String(20), default="per_person", nullable=False)
    is_default = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourCalendar(Base):
    __tablename__ = "tour_calendar"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    tour_date = Column(DateTime(timezone=True), nullable=False, index=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    available_seats = Column(Integer, default=0, nullable=False)
    booked_seats = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="available", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourUnavailableDate(Base):
    __tablename__ = "tour_unavailable_dates"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    unavailable_date = Column(DateTime(timezone=True), nullable=False, index=True)
    reason = Column(Text, default="", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourDiscount(Base):
    __tablename__ = "tour_discounts"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("tour_categories.id"), nullable=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    discount_name = Column(String(255), nullable=False)
    discount_code = Column(String(50), nullable=True, unique=True, index=True)
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Float, nullable=False)
    discount_scope = Column(String(20), default="tour", nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)
    minimum_booking_amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour", foreign_keys=[tour_id])
    category = relationship("TourCategory", foreign_keys=[category_id])
    country = relationship("Country", foreign_keys=[country_id])
