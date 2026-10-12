from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    notification_type = Column(String(60), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    message = Column(Text, nullable=False)
    channel = Column(String(30), default="in_app", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    is_read = Column(Integer, default=0, nullable=False, index=True)
    entity_type = Column(String(60), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    notification_id = Column(String(100), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    event_key = Column(String(100), nullable=True, index=True)
    event_version = Column(String(100), nullable=True)
    idempotency_key = Column(String(255), nullable=True, unique=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=True, index=True)
    channel = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NotificationDelivery(Base):
    """One email delivery reservation per business event and recipient."""
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_notification_delivery_idempotency"),)

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    recipient_type = Column(String(40), nullable=False)
    recipient_email = Column(String(180), nullable=False)
    template_key = Column(String(100), nullable=False)
    subject = Column(String(255), nullable=True)
    # The rendered-template inputs and fallback copy are retained so a failed
    # lifecycle message can be retried safely after a transient SMTP outage.
    payload_json = Column(JSON, nullable=True)
    status = Column(String(30), default="pending", nullable=False, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint_hash", name="uq_push_endpoint_hash"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Push service URLs can exceed 500 chars (e.g. Windows/Edge), so the URL
    # is TEXT and uniqueness is enforced on its SHA-256 (endpoint_hash).
    endpoint = Column(Text, nullable=False)
    endpoint_hash = Column(String(64), nullable=False)
    p256dh = Column(String(256), nullable=False)
    auth = Column(String(255), nullable=False)
    platform = Column(String(20), nullable=True)
    device_type = Column(String(30), nullable=True)
    is_active = Column(Integer, default=1, nullable=False, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PushDeliveryLog(Base):
    __tablename__ = "push_delivery_logs"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True)
    subscription_id = Column(Integer, ForeignKey("push_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_key = Column(String(100), nullable=True, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(30), default="web_push", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
