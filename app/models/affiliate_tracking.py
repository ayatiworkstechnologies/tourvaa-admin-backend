from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AffiliateLink(Base):
    """Unique referral links generated per affiliate."""
    __tablename__ = "affiliate_links"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    ref_code = Column(String(60), unique=True, nullable=False, index=True)
    destination_url = Column(String(500), nullable=True)
    label = Column(String(120), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")
    clicks = relationship("AffiliateClick", back_populates="link", cascade="all, delete-orphan")
    conversions = relationship("AffiliateConversion", back_populates="link", cascade="all, delete-orphan")


class AffiliateClick(Base):
    __tablename__ = "affiliate_clicks"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("affiliate_links.id"), nullable=False, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    referrer = Column(String(500), nullable=True)
    clicked_at = Column(DateTime(timezone=True), server_default=func.now())

    link = relationship("AffiliateLink", back_populates="clicks")


class AffiliateConversion(Base):
    __tablename__ = "affiliate_conversions"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("affiliate_links.id"), nullable=False, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True, index=True)
    booking_amount = Column(Numeric(12, 2), default=0, nullable=False)
    commission_percentage = Column(Numeric(5, 2), default=0, nullable=False)
    commission_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, confirmed, paid, reversed
    converted_at = Column(DateTime(timezone=True), server_default=func.now())

    link = relationship("AffiliateLink", back_populates="conversions")
    booking = relationship("Booking")


class AffiliatePayout(Base):
    __tablename__ = "affiliate_payouts"

    id = Column(Integer, primary_key=True, index=True)
    payout_code = Column(String(30), unique=True, nullable=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    total_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    payment_method = Column(String(50), default="bank_transfer", nullable=False)
    reference_number = Column(String(150), nullable=True)
    status = Column(String(30), default="pending", nullable=False, index=True)
    notes = Column(Text, nullable=True)
    initiated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate")
    initiator = relationship("User", foreign_keys=[initiated_by])
