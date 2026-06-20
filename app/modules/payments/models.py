from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_code = Column(String(30), unique=True, nullable=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    payment_method = Column(String(30), default="card", nullable=False)
    payment_type = Column(String(30), default="full", nullable=False)
    gateway = Column(String(50), default="manual", nullable=False)
    gateway_payment_id = Column(String(150), nullable=True, index=True)
    gateway_order_id = Column(String(150), nullable=True, index=True)
    idempotency_key = Column(String(150), nullable=True, unique=True, index=True)

    total_amount = Column(Numeric(12, 2), default=0, nullable=False)
    authorized_amount = Column(Numeric(12, 2), default=0, nullable=False)
    captured_amount = Column(Numeric(12, 2), default=0, nullable=False)
    paid_amount = Column(Numeric(12, 2), default=0, nullable=False)
    pending_amount = Column(Numeric(12, 2), default=0, nullable=False)
    gst_amount = Column(Numeric(12, 2), default=0, nullable=False)
    surcharge_amount = Column(Numeric(12, 2), default=0, nullable=False)
    refunded_amount = Column(Numeric(12, 2), default=0, nullable=False)

    payment_status = Column(String(30), default="pending", nullable=False, index=True)
    transaction_id = Column(String(100), nullable=True, index=True)
    payment_date = Column(String(30), nullable=True)

    notes = Column(Text, nullable=True)
    failure_reason = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking", back_populates="payments")
    customer = relationship("Customer", foreign_keys=[customer_id])
    creator = relationship("User", foreign_keys=[created_by])
    transactions = relationship("PaymentTransaction", back_populates="payment", cascade="all, delete-orphan")
    holds = relationship("PaymentHold", back_populates="payment", cascade="all, delete-orphan")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    transaction_type = Column(String(30), nullable=False)
    amount = Column(Numeric(12, 2), default=0, nullable=False)
    status = Column(String(30), default="success", nullable=False)
    gateway_reference = Column(String(150), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    payment = relationship("Payment", back_populates="transactions")


class PaymentHold(Base):
    __tablename__ = "payment_holds"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    hold_amount = Column(Numeric(12, 2), default=0, nullable=False)
    captured_amount = Column(Numeric(12, 2), default=0, nullable=False)
    released_amount = Column(Numeric(12, 2), default=0, nullable=False)
    status = Column(String(30), default="active", nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    payment = relationship("Payment", back_populates="holds")
