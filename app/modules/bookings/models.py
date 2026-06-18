from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String(30), unique=True, nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Denormalized fields so history survives tour edits
    tour_name = Column(String(255), default="", nullable=False)
    tour_date = Column(String(30), default="", nullable=False)
    country = Column(String(100), default="", nullable=False)
    supplier_name = Column(String(150), default="", nullable=False)

    no_of_adults = Column(Integer, default=1, nullable=False)
    no_of_children = Column(Integer, default=0, nullable=False)
    no_of_infants = Column(Integer, default=0, nullable=False)

    total_cost = Column(Numeric(12, 2), default=0, nullable=False)
    amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    amount_pending = Column(Numeric(12, 2), default=0, nullable=False)

    booking_status = Column(String(30), default="upcoming", nullable=False)
    payment_status = Column(String(30), default="pending", nullable=False)

    notes = Column(Text, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer", foreign_keys=[customer_id])
    tour = relationship("Tour", foreign_keys=[tour_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    creator = relationship("User", foreign_keys=[created_by])
    payments = relationship("Payment", back_populates="booking", cascade="all, delete-orphan")
