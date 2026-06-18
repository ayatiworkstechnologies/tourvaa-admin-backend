from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Affiliate(Base):
    __tablename__ = "affiliates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    affiliate_code = Column(String(30), unique=True, nullable=True, index=True)
    business_type = Column(String(75), default="", nullable=False)
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False, index=True)
    phone = Column(String(30), default="", nullable=False)
    website_url = Column(String(255), default="", nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    status = Column(String(20), default="inactive", nullable=False)
    approval_status = Column(String(30), default="pending", nullable=False, index=True)
    rejection_reason = Column(String(255), nullable=True)
    admin_comments = Column(Text, nullable=True)
    api_link = Column(String(255), default="", nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    country = relationship("Country")
    city = relationship("City")
    marketing_info = relationship("AffiliateMarketingInfo", back_populates="affiliate", uselist=False, cascade="all, delete-orphan")
    invoicing = relationship("AffiliateInvoicing", back_populates="affiliate", uselist=False, cascade="all, delete-orphan")
    documents = relationship("AffiliateDocument", back_populates="affiliate", cascade="all, delete-orphan")


class AffiliateMarketingInfo(Base):
    __tablename__ = "affiliate_marketing_info"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, unique=True, index=True)
    promotion_methods = Column(Text, default="", nullable=False)
    estimated_monthly_bookings = Column(Integer, default=0, nullable=False)
    existing_audience_size = Column(Integer, default=0, nullable=False)
    social_media_profiles = Column(Text, default="", nullable=False)
    existing_travel_platforms_used = Column(Text, default="", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate", back_populates="marketing_info")


class AffiliateInvoicing(Base):
    __tablename__ = "affiliate_invoicing"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, unique=True, index=True)
    contact_name = Column(String(150), default="", nullable=False)
    email = Column(String(150), default="", nullable=False)
    phone = Column(String(30), default="", nullable=False)
    account_name = Column(String(150), default="", nullable=False)
    account_number = Column(String(100), default="", nullable=False)
    bank_name = Column(String(150), default="", nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True)
    tax_number = Column(String(100), default="", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    affiliate = relationship("Affiliate", back_populates="invoicing")


class AffiliateDocument(Base):
    __tablename__ = "affiliate_documents"

    id = Column(Integer, primary_key=True, index=True)
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    document_type = Column(String(100), nullable=False)
    document_name = Column(String(150), nullable=False)
    file_path = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    mime_type = Column(String(100), default="", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    affiliate = relationship("Affiliate", back_populates="documents")
