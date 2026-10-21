from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Conversation(Base):
    """One thread per portal user talking to Tourvaa Admin support.

    A single conversation per (participant_type, participant_user_id) keeps
    the admin inbox simple: one row per person, tabbed by role, rather than
    a subject-per-thread model nobody asked for.
    """
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("participant_user_id", name="uq_conversation_participant_user"),)

    id = Column(Integer, primary_key=True, index=True)
    participant_type = Column(String(20), nullable=False, index=True)  # agent | supplier | customer | affiliate
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
    sender_role = Column(String(20), nullable=False)  # admin | agent | supplier | customer | affiliate
    body = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    # Persisted delivery/read state is intentionally minimal: each support
    # conversation has one portal participant and the Tourvaa admin team.
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")


class BookingConversation(Base):
    """Persistence container for role-isolated, booking-specific Admin chat.

    The initiator and supplier share the booking reference, but serializers
    expose only their own messages and Admin replies addressed to their role.
    """
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
    sender_role = Column(String(20), nullable=False)  # customer | agent | supplier | admin
    # Admin replies are addressed to one booking party so the Admin console
    # can keep Supplier and Agent/Customer threads distinct.
    recipient_role = Column(String(20), nullable=True)  # supplier | customer | agent
    body = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    conversation = relationship("BookingConversation", back_populates="messages")
    sender = relationship("User")
