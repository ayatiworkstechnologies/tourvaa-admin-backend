from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class RefundRule(Base):
    # policy rules per tour (or global if tour_id is null), can be tiered
    # e.g. >30 days before = 100% refund, 7-30 days = 50%, <7 days = 0%
    __tablename__ = "refund_rules"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)
    # Days before tour start date
    days_before_tour_min = Column(Integer, nullable=False)
    days_before_tour_max = Column(Integer, nullable=True)
    # NULL max means "any amount of days before"
    refund_percentage = Column(Numeric(5, 2), nullable=False, default=0)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")


class CancellationRequest(Base):
    __tablename__ = "cancellation_requests"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)

    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, approved, rejected, refund_processed

    # Calculated refund
    refund_percentage = Column(Numeric(5, 2), default=0, nullable=False)
    refund_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    # Admin decision
    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Gateway refund tracking
    gateway_refund_id = Column(String(150), nullable=True)
    refund_processed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking")
    customer = relationship("Customer")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
