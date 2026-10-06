from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, true as sa_true
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
    why_choose_this_tour = Column(Text, nullable=True)
    ideal_for = Column(Text, nullable=True)
    best_season = Column(String(150), nullable=True)
    tour_pace = Column(String(50), nullable=True)
    transportation_summary = Column(Text, nullable=True)
    accommodation_summary = Column(Text, nullable=True)
    meal_summary = Column(Text, nullable=True)
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
    optional_activities = Column(Text, default="", nullable=True)
    accommodation = Column(String(255), default="", nullable=True)
    start_time = Column(String(20), nullable=True)
    end_time = Column(String(20), nullable=True)
    travel_distance = Column(String(100), nullable=True)
    travel_duration = Column(String(100), nullable=True)
    transport_type = Column(String(100), nullable=True)
    meals_included = Column(String(150), nullable=True)
    important_notes = Column(Text, nullable=True)
    image = Column(String(255), default="", nullable=False)
    image_alt_text = Column(String(180), default="", nullable=False)
    # JSON-encoded list of image paths for the day's carousel (mirrors
    # SupplierVehicle.vehicle_photos' JSON-string-array pattern) - `image`
    # above stays as the single cover/fallback image for backward
    # compatibility with existing callers (e.g. itinerary_pdf.py).
    images = Column(Text, default="[]", nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    # "standard" (default) or "free_day" - an explicit admin flag for free /
    # leisure days, which the public tour page can pair with optional
    # external "things to do" suggestions. Never inferred from the title.
    day_type = Column(String(20), default="standard", server_default="standard", nullable=False)
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
    extra_price = Column(Numeric(12, 2), default=0, nullable=False)
    price_type = Column(String(20), default="per_booking", nullable=False)
    category = Column(String(30), default="other", nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    # When False, this extension's price is excluded from the commissionable
    # portion of the booking's supplier gross share -- see
    # services.bookings.compute_booking_supplier_financials /
    # Booking.non_commissionable_addon_amount. Defaults True to preserve
    # existing behavior (commission applies to all addons) exactly.
    commissionable = Column(Boolean, default=True, nullable=False, server_default=sa_true())
    # Cost-plus margin model: when set, this is the supplier's exact cost for
    # this item, paid verbatim (quantity * supplier_cost), with NO commission
    # percentage applied -- mutually exclusive with the commissionable flag
    # above, which drives the percentage-commission model instead. NULL (the
    # default) means "no cost-plus margin configured", falling back to the
    # commissionable/commission-percentage behavior exactly as before this
    # column existed. See services.bookings._price_booking /
    # compute_booking_supplier_financials.
    supplier_cost = Column(Numeric(12, 2), nullable=True)
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


class TourPricing(Base):
    __tablename__ = "tour_pricing"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    passenger_from = Column(Integer, nullable=False)
    passenger_to = Column(Integer, nullable=False)
    adult_price = Column(Numeric(12, 2), nullable=False)
    child_price = Column(Numeric(12, 2), default=0, nullable=False)
    supplier_price = Column(Numeric(12, 2), default=0, nullable=False)
    final_price = Column(Numeric(12, 2), nullable=False)
    supplier_final_adult_price = Column(Numeric(12, 2), nullable=True)
    supplier_final_child_price = Column(Numeric(12, 2), nullable=True)
    # The supplier's own agreed commission rate for THIS slab, floor-
    # enforced against resolve_effective_commission_percentage (Tour >
    # Supplier > platform minimum) - null means "use that resolved floor
    # directly". supplier_final_*_price = *_price * (1 - this/100).
    commission_percentage = Column(Numeric(5, 2), nullable=True)
    # Tourvaa's admin-only markup (percentage) on top of the supplier's
    # adult_price/child_price. Never visible to or settable by suppliers
    # (stripped in routers.tours._for_actor, ignored from supplier payloads).
    #   storefront_*_price     = *_price * (1 + markup%)   <- customer pays
    #   supplier_final_*_price = *_price * (1 - commission%) <- supplier gets
    # Tourvaa earns markup + commission. 0 = storefront equals supplier price.
    # NULL = no slab-specific markup: follows the platform default
    # (default_admin_markup_percentage) -- see services/markup.py.
    admin_markup_type = Column(String(20), default="percentage", nullable=False)
    admin_markup_value = Column(Numeric(12, 2), nullable=True)
    # Customer-facing prices, always derived from the fields above (never
    # client-supplied). Public pricing and checkout read these.
    storefront_adult_price = Column(Numeric(12, 2), nullable=True)
    storefront_child_price = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TourDatePrice(Base):
    """A per-date selling-price override for a tour, layered on top of the
    normal TourPricing slab -- e.g. a peak-season surcharge or off-peak
    discount for a specific departure date. When present for a booking's
    date, adult_price/child_price here replace the slab's supplier prices
    (the resolved slab's admin markup is still added on top for the
    customer price), Tourvaa's commission is deducted from them, and the
    booking snapshots price_source=DATE_OVERRIDE plus the resolved unit
    prices so settlement never re-reads this row."""
    __tablename__ = "tour_date_prices"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    price_date = Column(Date, nullable=False, index=True)
    adult_price = Column(Numeric(12, 2), nullable=False)
    child_price = Column(Numeric(12, 2), default=0, nullable=False)
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
    price_per_person = Column(Numeric(12, 2), default=0, nullable=False)
    child_price_per_person = Column(Numeric(12, 2), nullable=True)
    infant_price_per_person = Column(Numeric(12, 2), nullable=True)
    pricing_mode = Column(String(20), default="flat", nullable=False)
    image = Column(String(255), default="", nullable=False)
    category = Column(String(30), default="other", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    # See TourExtension.commissionable above.
    commissionable = Column(Boolean, default=True, nullable=False, server_default=sa_true())
    # See TourExtension.supplier_cost above.
    supplier_cost = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class TourAccommodationExtra(Base):
    __tablename__ = "tour_accommodation_extras"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    accommodation_name = Column(String(255), nullable=False)
    description = Column(Text, default="", nullable=True)
    extra_price = Column(Numeric(12, 2), default=0, nullable=False)
    price_type = Column(String(20), default="per_person", nullable=False)
    image = Column(String(255), default="", nullable=True)
    category = Column(String(30), default="room_upgrade", nullable=False)
    is_default = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    # See TourExtension.commissionable above.
    commissionable = Column(Boolean, default=True, nullable=False, server_default=sa_true())
    # See TourExtension.supplier_cost above.
    supplier_cost = Column(Numeric(12, 2), nullable=True)
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


class TourAvailabilityConfig(Base):
    """Recurring-availability schedule a supplier/admin defines once
    (Tour Start/End Date, minimum advance booking window, and a Weekly/
    Fortnightly/Monthly frequency) - services.tour_availability expands this
    into concrete TourCalendar rows rather than requiring every date to be
    added by hand."""

    __tablename__ = "tour_availability_configs"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, unique=True, index=True)
    availability_start_date = Column(DateTime(timezone=True), nullable=True)
    availability_end_date = Column(DateTime(timezone=True), nullable=True)
    min_advance_booking_days = Column(Integer, default=0, nullable=False)
    # How many weeks before the min-advance-booking cutoff date an agent may
    # still Reserve Now, Pay Later; closer than that they only see Pay in
    # Full Today. See services.tour_availability.agent_reserve_eligibility.
    agent_no_deposit_buffer_weeks = Column(Integer, default=4, nullable=False)
    # Legacy, retained only for existing database compatibility. Reserve Now
    # is now an invoice/pay-later flow and never reads this value.
    agent_reserve_deposit_percentage = Column(Float, default=30.0, nullable=False)
    # "weekly" | "fortnightly" | "monthly", NULL until a schedule is saved.
    frequency = Column(String(20), nullable=True)
    # Fortnightly: 1 = the week of the start date, 2 = the following week. Unused for weekly.
    # Monthly: kept as the first selected week for older clients; see frequency_weeks.
    frequency_week = Column(Integer, nullable=True)
    # Monthly: which occurrence(s) of each chosen weekday to run, 1-4 = 1st-4th and
    # 5 = the last one in the month, e.g. [1, 3] with Saturday = 1st and 3rd Saturday.
    frequency_weeks = Column(JSON, nullable=True)
    # ISO weekday ints (0=Monday..6=Sunday) the tour operates on.
    frequency_days = Column(JSON, nullable=True)
    # Capacity applied to each generated TourCalendar row.
    seats_per_occurrence = Column(Integer, default=0, nullable=False)
    last_end_date_reminder_at = Column(DateTime(timezone=True), nullable=True)
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
    discount_value = Column(Numeric(12, 2), nullable=False)
    discount_scope = Column(String(20), default="tour", nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)
    minimum_booking_amount = Column(Numeric(12, 2), default=0, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    # Who actually absorbs this promo code's discount amount: "SUPPLIER" (the
    # default -- current/legacy behavior, unchanged) or "TOURVAA". Note that
    # unlike group discounts, promo discounts currently don't feed into the
    # supplier commission calc at all (see compute_booking_supplier_financials),
    # so this only matters for future Tourvaa-net-revenue accounting -- it is
    # still snapshotted onto the booking (Booking.promo_discount_funded_by).
    funded_by = Column(String(20), default="SUPPLIER", nullable=False, server_default="SUPPLIER")
    # Promo codes only: list this code publicly (tour page + checkout
    # "Available offers") so customers can apply it with one click. Off =
    # private code that works only when typed (newsletter, partner, agent
    # codes). Automatic (code-free) discounts are always shown. See
    # services.discounts.list_public_offers.
    show_on_website = Column(Boolean, default=True, nullable=False, server_default=sa_true())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour", foreign_keys=[tour_id])
    category = relationship("TourCategory", foreign_keys=[category_id])
    country = relationship("Country", foreign_keys=[country_id])


class TourDiscountHistory(Base):
    """Append-only version log for TourDiscount. Editing a discount no longer
    mutates it freely (see services.tours.amend_discount) -- only extending
    the validity window or changing the percentage/value is allowed, and each
    such change writes a new row here (version_number incrementing) instead
    of just overwriting the live TourDiscount row silently. The live
    TourDiscount row is still updated in place so existing pricing/display
    code (_active_discount, storefront pricing) keeps reading current values
    without any change; this table exists purely as the audit trail."""

    __tablename__ = "tour_discount_history"

    id = Column(Integer, primary_key=True, index=True)
    discount_id = Column(Integer, ForeignKey("tour_discounts.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    change_type = Column(String(30), nullable=False)  # created | validity_extended | percentage_changed
    discount_name = Column(String(255), nullable=False)
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Numeric(12, 2), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String(500), nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    discount = relationship("TourDiscount", foreign_keys=[discount_id])
    changed_by_user = relationship("User", foreign_keys=[changed_by])


class TourGroupDiscountTier(Base):
    """Supplier-defined group-size discount, scoped to the whole Tour (not a
    single TourPricing slab). When a booking's total traveller count
    (adults + children) falls within [min_pax, max_pax], this tier's
    discount is applied once to the booking's base slab amount, before any
    TourDiscount promo code, so it is a separate concept from TourDiscount.
    See services.bookings._price_booking for where this is consumed."""

    __tablename__ = "tour_group_discount_tiers"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    min_pax = Column(Integer, nullable=False)
    max_pax = Column(Integer, nullable=False)
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    # Who absorbs this group discount: "SUPPLIER" (default -- current
    # behavior, the discount ratio also reduces the supplier's net_earnings
    # via compute_supplier_commission_breakdown's group_discount_ratio) or
    # "TOURVAA" (supplier is paid as if the discount never happened --
    # see compute_booking_supplier_financials, which zeroes the ratio when
    # the booking's snapshotted Booking.group_discount_funded_by == "TOURVAA").
    funded_by = Column(String(20), default="SUPPLIER", nullable=False, server_default="SUPPLIER")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")
