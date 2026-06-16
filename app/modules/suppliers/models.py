from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    supplier_code = Column(String(30), unique=True, nullable=True, index=True)
    supplier_name = Column(String(150), nullable=False)
    supplier_type = Column(String(75), default="", nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    years_in_operation = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="inactive", nullable=False)
    approval_status = Column(String(30), default="pending", nullable=False, index=True)
    rejection_reason = Column(String(255), nullable=True)
    admin_comments = Column(Text, nullable=True)
    pending_requirements = Column(Text, nullable=True)
    markup_type = Column(String(20), nullable=True)
    markup_value = Column(Float, default=0, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    country = relationship("Country")
    city = relationship("City")
    contacts = relationship("SupplierContact", back_populates="supplier", cascade="all, delete-orphan")
    business_info = relationship("SupplierBusinessInfo", back_populates="supplier", uselist=False, cascade="all, delete-orphan")
    vehicles = relationship("SupplierVehicle", back_populates="supplier", cascade="all, delete-orphan")
    invoicing = relationship("SupplierInvoicing", back_populates="supplier", uselist=False, cascade="all, delete-orphan")
    documents = relationship("SupplierDocument", back_populates="supplier", cascade="all, delete-orphan")


class SupplierContact(Base):
    __tablename__ = "supplier_contacts"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    contact_name = Column(String(150), nullable=False)
    designation = Column(String(100), default="", nullable=False)
    phone = Column(String(30), default="", nullable=False)
    email = Column(String(150), default="", nullable=False)
    alternate_phone = Column(String(30), default="", nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier", back_populates="contacts")


class SupplierBusinessInfo(Base):
    __tablename__ = "supplier_business_info"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, unique=True, index=True)
    years_in_business = Column(Integer, default=0, nullable=False)
    certificate_of_incorporation = Column(String(255), default="", nullable=False)
    monthly_customers_count = Column(Integer, default=0, nullable=False)
    target_market = Column(String(255), default="", nullable=False)
    destinations_sold = Column(Text, default="", nullable=False)
    gst_tax_number = Column(String(100), default="", nullable=False)
    business_registration_number = Column(String(100), default="", nullable=False)
    approval_status = Column(String(30), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier", back_populates="business_info")


class SupplierVehicle(Base):
    __tablename__ = "supplier_vehicles"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    make = Column(String(100), default="", nullable=False)
    model = Column(String(100), default="", nullable=False)
    year = Column(Integer, nullable=True)
    capacity = Column(Integer, nullable=True)
    fitness_certificate = Column(String(255), default="", nullable=False)
    insurance_document = Column(String(255), default="", nullable=False)
    vehicle_photos = Column(Text, default="", nullable=False)
    approval_status = Column(String(30), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier", back_populates="vehicles")


class SupplierInvoicing(Base):
    __tablename__ = "supplier_invoicing"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, unique=True, index=True)
    contact_name = Column(String(150), default="", nullable=False)
    email = Column(String(150), default="", nullable=False)
    phone = Column(String(30), default="", nullable=False)
    account_name = Column(String(150), default="", nullable=False)
    account_number = Column(String(100), default="", nullable=False)
    bank_name = Column(String(150), default="", nullable=False)
    bank_branch = Column(String(150), default="", nullable=False)
    swift_code = Column(String(50), default="", nullable=False)
    iban = Column(String(100), default="", nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True)
    tax_number = Column(String(100), default="", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier", back_populates="invoicing")


class SupplierDocument(Base):
    __tablename__ = "supplier_documents"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    document_type = Column(String(100), nullable=False)
    document_name = Column(String(150), nullable=False)
    file_path = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    mime_type = Column(String(100), default="", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    rejection_reason = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    supplier = relationship("Supplier", back_populates="documents")
