from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String(30), unique=True, nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)
    tour_calendar_id = Column(Integer, ForeignKey("tour_calendar.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    booked_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    booking_source = Column(String(30), default="admin", nullable=False, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)

    tour_name = Column(String(255), default="", nullable=False)
    tour_date = Column(String(30), default="", nullable=False)
    country = Column(String(100), default="", nullable=False)
    supplier_name = Column(String(150), default="", nullable=False)
    tour_start_date = Column(DateTime(timezone=True), nullable=True, index=True)
    tour_end_date = Column(DateTime(timezone=True), nullable=True)

    no_of_adults = Column(Integer, default=1, nullable=False)
    no_of_children = Column(Integer, default=0, nullable=False)
    no_of_infants = Column(Integer, default=0, nullable=False)
    adults_count = Column(Integer, default=1, nullable=False)
    children_count = Column(Integer, default=0, nullable=False)
    total_travellers = Column(Integer, default=1, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    total_cost = Column(Numeric(12, 2), default=0, nullable=False)
    base_amount = Column(Numeric(12, 2), default=0, nullable=False)
    optional_activity_amount = Column(Numeric(12, 2), default=0, nullable=False)
    accommodation_amount = Column(Numeric(12, 2), default=0, nullable=False)
    extension_amount = Column(Numeric(12, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(12, 2), default=0, nullable=False)
    promo_code = Column(String(100), nullable=True)
    tax_amount = Column(Numeric(12, 2), default=0, nullable=False)
    surcharge_amount = Column(Numeric(12, 2), default=0, nullable=False)
    final_amount = Column(Numeric(12, 2), default=0, nullable=False)
    amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    amount_pending = Column(Numeric(12, 2), default=0, nullable=False)

    booking_status = Column(String(30), default="draft", nullable=False, index=True)
    supplier_acceptance_status = Column(String(30), default="not_assigned", nullable=False, index=True)
    payment_status = Column(String(30), default="unpaid", nullable=False, index=True)
    payment_type = Column(String(30), default="full", nullable=False)

    notes = Column(Text, nullable=True)
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer", foreign_keys=[customer_id])
    agent = relationship("Agent", foreign_keys=[agent_id])
    tour = relationship("Tour", foreign_keys=[tour_id])
    calendar = relationship("TourCalendar", foreign_keys=[tour_calendar_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    creator = relationship("User", foreign_keys=[created_by])
    payments = relationship("Payment", back_populates="booking", cascade="all, delete-orphan")
    travellers = relationship("BookingTraveller", back_populates="booking", cascade="all, delete-orphan")
    optional_activities = relationship("BookingOptionalActivity", back_populates="booking", cascade="all, delete-orphan")
    accommodations = relationship("BookingAccommodation", back_populates="booking", cascade="all, delete-orphan")
    extensions = relationship("BookingExtension", back_populates="booking", cascade="all, delete-orphan")
    status_history = relationship("BookingStatusHistory", back_populates="booking", cascade="all, delete-orphan")
    communications = relationship("BookingCommunication", back_populates="booking", cascade="all, delete-orphan")


class BookingTraveller(Base):
    __tablename__ = "booking_travellers"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    traveller_type = Column(String(20), nullable=False)
    first_name = Column(String(100), default="", nullable=False)
    last_name = Column(String(100), default="", nullable=False)
    full_name = Column(String(220), default="", nullable=False)
    date_of_birth = Column(DateTime(timezone=True), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(30), nullable=True)
    nationality = Column(String(100), nullable=True)
    passport_number = Column(String(100), nullable=True)
    passport_expiry_date = Column(DateTime(timezone=True), nullable=True)
    email = Column(String(150), nullable=True)
    phone = Column(String(50), nullable=True)
    is_primary_contact = Column(Integer, default=0, nullable=False)
    special_requirements = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking", back_populates="travellers")


class BookingOptionalActivity(Base):
    __tablename__ = "booking_optional_activities"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    tour_optional_activity_id = Column(Integer, ForeignKey("tour_optional_activities.id"), nullable=True)
    activity_name_snapshot = Column(String(255), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Numeric(12, 2), default=0, nullable=False)
    total_price = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="optional_activities")


class BookingAccommodation(Base):
    __tablename__ = "booking_accommodations"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    tour_accommodation_extra_id = Column(Integer, ForeignKey("tour_accommodation_extras.id"), nullable=True)
    accommodation_name_snapshot = Column(String(255), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    price_type = Column(String(30), default="per_person", nullable=False)
    unit_price = Column(Numeric(12, 2), default=0, nullable=False)
    total_price = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="accommodations")


class BookingExtension(Base):
    __tablename__ = "booking_extensions"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    tour_extension_id = Column(Integer, ForeignKey("tour_extensions.id"), nullable=True)
    extension_tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True)
    extension_name_snapshot = Column(String(255), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Numeric(12, 2), default=0, nullable=False)
    total_price = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="extensions")


class BookingStatusHistory(Base):
    __tablename__ = "booking_status_history"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    changed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    change_source = Column(String(30), default="admin", nullable=False)
    reason = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="status_history")


class BookingCommunication(Base):
    __tablename__ = "booking_communications"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    sender_type = Column(String(30), default="admin", nullable=False)
    message_type = Column(String(30), default="admin_message", nullable=False)
    subject = Column(String(255), default="", nullable=False)
    message = Column(Text, nullable=False)
    visibility = Column(String(30), default="internal", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking", back_populates="communications")
    replies = relationship("MessageReply", back_populates="communication", cascade="all, delete-orphan")


class MessageReply(Base):
    __tablename__ = "message_replies"

    id = Column(Integer, primary_key=True, index=True)
    communication_id = Column(Integer, ForeignKey("booking_communications.id"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    sender_type = Column(String(30), default="admin", nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    communication = relationship("BookingCommunication", back_populates="replies")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    recipient_email = Column(String(180), nullable=False)
    subject = Column(String(255), nullable=False)
    template_key = Column(String(100), nullable=True)
    entity_type = Column(String(60), nullable=True)
    entity_id = Column(Integer, nullable=True)
    status = Column(String(30), default="pending", nullable=False)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
