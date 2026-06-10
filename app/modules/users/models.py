from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    phone = Column(String(30), default="", nullable=False)
    profile_image = Column(String(255), default="", nullable=False)
    address = Column(String(255), default="", nullable=False)
    country = Column(String(100), default="", nullable=False)
    state = Column(String(100), default="", nullable=False)
    city = Column(String(100), default="", nullable=False)
    pincode = Column(String(20), default="", nullable=False)
    password = Column(String(255), nullable=False)

    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)

    is_active = Column(Boolean, default=True)
    approval_status = Column(String(20), default="approved", nullable=False)
    reset_password_token = Column(String(255), nullable=True)
    reset_password_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role = relationship("Role", back_populates="users")
