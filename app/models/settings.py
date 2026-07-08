from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    label = Column(String(150), nullable=False)
    group = Column(String(80), default="general", nullable=False)
    is_public = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaymentSetting(Base):
    __tablename__ = "payment_settings"

    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(100), unique=True, nullable=False, index=True)
    is_enabled = Column(Boolean, default=False, nullable=False)
    public_key = Column(Text, nullable=True)
    secret_key = Column(Text, nullable=True)
    surcharge_percentage = Column(String(20), default="0", nullable=False)
    mode = Column(String(20), default="test", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ApiSetting(Base):
    __tablename__ = "api_settings"

    id = Column(Integer, primary_key=True, index=True)
    api_name = Column(String(100), unique=True, nullable=False, index=True)
    api_key = Column(Text, nullable=True)
    api_secret = Column(Text, nullable=True)
    api_url = Column(Text, nullable=True)
    is_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
