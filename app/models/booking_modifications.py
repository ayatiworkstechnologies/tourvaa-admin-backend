from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class BookingModificationRequest(Base):
    __tablename__ = "booking_modification_requests"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False, index=True)
    requester_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    requester_type = Column(String(30), nullable=False)
    proposed_changes = Column(JSON, nullable=False)
    original_values = Column(JSON, nullable=False)
    reason = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decision_reason = Column(Text, nullable=True)
    decision_history = Column(JSON, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking")
    requester = relationship("User", foreign_keys=[requester_user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
