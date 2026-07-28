from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class TourReview(Base):
    # One review per booking (not per tour) - a customer can rebook the same
    # tour later and leave a second review for that later trip.
    __tablename__ = "tour_reviews"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    review_text = Column(Text, nullable=True)
    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking")
    customer = relationship("Customer")
    tour = relationship("Tour")

    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_tour_reviews_booking"),
    )
