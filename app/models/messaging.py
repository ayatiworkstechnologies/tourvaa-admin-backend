from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Conversation(Base):
    """One thread per agent/supplier/customer user talking to admin support.

    A single conversation per (participant_type, participant_user_id) keeps
    the admin inbox simple: one row per person, tabbed by role, rather than
    a subject-per-thread model nobody asked for.
    """
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("participant_user_id", name="uq_conversation_participant_user"),)

    id = Column(Integer, primary_key=True, index=True)
    participant_type = Column(String(20), nullable=False, index=True)  # agent | supplier | customer
    participant_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), default="open", nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview = Column(String(300), nullable=True)
    admin_unread_count = Column(Integer, default=0, nullable=False)
    participant_unread_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    participant_user = relationship("User")
    messages = relationship("Message", back_populates="conversation", order_by="Message.id", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    sender_role = Column(String(20), nullable=False)  # admin | agent | supplier | customer
    body = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")


class BookingConversation(Base):
    """Direct thread about one booking between whoever booked it (the
    customer, or the agent who booked on their behalf) and the supplier
    fulfilling it. Separate from Conversation (which is always "this
    person <-> admin support") because here neither side is admin, and a
    thread only makes sense in the context of one specific booking."""
    __tablename__ = "booking_conversations"
    __table_args__ = (UniqueConstraint("booking_id", "initiator_user_id", "supplier_user_id", name="uq_booking_conv_parties"),)

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    initiator_role = Column(String(20), nullable=False)  # customer | agent
    initiator_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplier_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), default="open", nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview = Column(String(300), nullable=True)
    initiator_unread_count = Column(Integer, default=0, nullable=False)
    supplier_unread_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking")
    initiator_user = relationship("User", foreign_keys=[initiator_user_id])
    supplier_user = relationship("User", foreign_keys=[supplier_user_id])
    messages = relationship("BookingMessage", back_populates="conversation", order_by="BookingMessage.id", cascade="all, delete-orphan")


class BookingMessage(Base):
    __tablename__ = "booking_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("booking_conversations.id"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    sender_role = Column(String(20), nullable=False)  # customer | agent | supplier
    body = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    conversation = relationship("BookingConversation", back_populates="messages")
    sender = relationship("User")
