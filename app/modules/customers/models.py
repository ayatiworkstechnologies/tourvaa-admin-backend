from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    customer_code = Column(String(30), unique=True, nullable=True, index=True)
    first_name = Column(String(75), default="", nullable=False)
    last_name = Column(String(75), default="", nullable=False)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    phone = Column(String(30), default="", nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    address_line_1 = Column(String(255), default="", nullable=False)
    address_line_2 = Column(String(255), default="", nullable=False)
    postal_code = Column(String(20), default="", nullable=False)
    address = Column(String(255), default="", nullable=False)
    profile_image = Column(String(255), default="", nullable=False)
    country = Column(String(100), default="", nullable=False)
    state = Column(String(100), default="", nullable=False)
    city = Column(String(100), default="", nullable=False)
    pincode = Column(String(20), default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    is_blocked = Column(Boolean, default=False, nullable=False)
    blocked_reason = Column(String(255), nullable=True)
    blocked_at = Column(DateTime(timezone=True), nullable=True)
    blocked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    total_bookings = Column(Integer, default=0, nullable=False)
    completed_bookings = Column(Integer, default=0, nullable=False)
    cancelled_bookings = Column(Integer, default=0, nullable=False)
    upcoming_bookings = Column(Integer, default=0, nullable=False)
    total_amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    total_amount_pending = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    blocker = relationship("User", foreign_keys=[blocked_by])
    country_ref = relationship("Country", foreign_keys=[country_id])
    city_ref = relationship("City", foreign_keys=[city_id])
    communications = relationship(
        "CustomerCommunication",
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class CustomerCommunication(Base):
    __tablename__ = "customer_communications"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    booking_id = Column(Integer, nullable=True, index=True)
    subject = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    sent_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    sent_to_email = Column(String(150), nullable=False)
    message_type = Column(String(30), default="admin_message", nullable=False)
    email_status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", back_populates="communications")
    sender = relationship("User")
