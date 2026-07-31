from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AgentLedger(Base):
    """One row per booking - tracks commission owed to the agent.

    Mirrors SupplierLedger. Commission here is the admin-approved
    Agent.discount_type/discount_value rate applied to the booking's gross
    value - the same figure the agent dashboard already estimates live via
    dashboard.py's commission_earned calculation, but snapshotted per
    booking so it stops moving if the agent's rate changes later, and so
    it can actually be paid out and tracked rather than just displayed.
    Does not cover agent_markup, which the agent already prices directly
    into customer_selling_price on the booking itself.
    """
    __tablename__ = "agent_ledgers"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)

    gross_amount = Column(Numeric(12, 2), default=0, nullable=False)
    commission_amount = Column(Numeric(12, 2), default=0, nullable=False)
    commission_percentage = Column(Numeric(5, 2), default=0, nullable=False)
    # Net payable to agent (== commission_amount; kept for symmetry with SupplierLedger)
    net_payable = Column(Numeric(12, 2), default=0, nullable=False)
    amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    amount_pending = Column(Numeric(12, 2), default=0, nullable=False)

    currency = Column(String(10), default="USD", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, partial, paid, refunded, reserved

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent")
    booking = relationship("Booking")


class AgentPayout(Base):
    """A batch payout from Tourvaa admin to an agent."""
    __tablename__ = "agent_payouts"

    id = Column(Integer, primary_key=True, index=True)
    payout_code = Column(String(30), unique=True, nullable=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)

    total_amount = Column(Numeric(12, 2), default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    payment_method = Column(String(50), default="bank_transfer", nullable=False)
    reference_number = Column(String(150), nullable=True)

    status = Column(String(30), default="pending", nullable=False, index=True)
    # pending, approved, paid, cancelled

    notes = Column(Text, nullable=True)
    initiated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent")
    initiator = relationship("User", foreign_keys=[initiated_by])
    approver = relationship("User", foreign_keys=[approved_by])
    payer = relationship("User", foreign_keys=[paid_by])
    items = relationship("AgentPayoutItem", back_populates="payout", cascade="all, delete-orphan")


class AgentPayoutItem(Base):
    """Links a payout to specific ledger entries."""
    __tablename__ = "agent_payout_items"

    id = Column(Integer, primary_key=True, index=True)
    payout_id = Column(Integer, ForeignKey("agent_payouts.id"), nullable=False, index=True)
    ledger_id = Column(Integer, ForeignKey("agent_ledgers.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    payout = relationship("AgentPayout", back_populates="items")
    ledger = relationship("AgentLedger")
