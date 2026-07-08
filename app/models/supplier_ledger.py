from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SupplierLedger(Base):
    """One row per booking — tracks what is owed to the supplier."""
    __tablename__ = "supplier_ledgers"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)

    # Gross amount charged to customer for this booking
    gross_amount = Column(Numeric(12, 2), default=0, nullable=False)
    # Tourvaa commission/markup
    commission_amount = Column(Numeric(12, 2), default=0, nullable=False)
    commission_percentage = Column(Numeric(5, 2), default=0, nullable=False)
    # Net payable to supplier = gross - commission
    net_payable = Column(Numeric(12, 2), default=0, nullable=False)
    # Amount already paid via payouts
    amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    amount_pending = Column(Numeric(12, 2), default=0, nullable=False)

    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, partial, paid, refunded

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier")
    booking = relationship("Booking")


class SupplierPayout(Base):
    """A batch payout from Tourvaa admin to a supplier."""
    __tablename__ = "supplier_payouts"

    id = Column(Integer, primary_key=True, index=True)
    payout_code = Column(String(30), unique=True, nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)

    total_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    payment_method = Column(String(50), default="bank_transfer", nullable=False)
    reference_number = Column(String(150), nullable=True)

    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, approved, paid, cancelled

    notes = Column(Text, nullable=True)
    initiated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier")
    initiator = relationship("User", foreign_keys=[initiated_by])
    approver = relationship("User", foreign_keys=[approved_by])
    items = relationship("SupplierPayoutItem", back_populates="payout", cascade="all, delete-orphan")


class SupplierPayoutItem(Base):
    """Links a payout to specific ledger entries."""
    __tablename__ = "supplier_payout_items"

    id = Column(Integer, primary_key=True, index=True)
    payout_id = Column(Integer, ForeignKey("supplier_payouts.id"), nullable=False, index=True)
    ledger_id = Column(Integer, ForeignKey("supplier_ledgers.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    payout = relationship("SupplierPayout", back_populates="items")
    ledger = relationship("SupplierLedger")
