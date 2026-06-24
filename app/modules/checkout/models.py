from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class CheckoutSession(Base):
    """
    Persists checkout state so a guest can log in / register mid-funnel
    and resume exactly where they left off.
    """
    __tablename__ = "checkout_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_key = Column(String(64), unique=True, nullable=False, index=True)
    # Null until the user is identified
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)
    tour_calendar_id = Column(Integer, ForeignKey("tour_calendar.id"), nullable=True)

    # Current step: tour_selection, travellers, extras, payment
    step = Column(String(50), default="tour_selection", nullable=False)
    status = Column(String(30), default="active", nullable=False, index=True)
    # active, completed, abandoned

    # Full checkout payload stored as JSON (travellers, extras, pricing, promo, etc.)
    data = Column(JSON, nullable=True)

    # Set once a booking is created from this session
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    tour = relationship("Tour")
    booking = relationship("Booking")
