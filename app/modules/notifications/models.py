from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
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
