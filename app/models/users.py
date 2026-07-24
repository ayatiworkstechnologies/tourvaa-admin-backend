from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.customers import Customer


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
    password = Column(String(255), nullable=True)

    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True, index=True)

    is_active = Column(Boolean, default=True, index=True)
    approval_status = Column(String(30), default="approved", nullable=False, index=True)
    user_type = Column(String(20), nullable=True, index=True)
    country_code = Column(String(8), default="", nullable=False)
    mobile_number = Column(String(20), nullable=True, unique=True, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    password_created_at = Column(DateTime(timezone=True), nullable=True)
    account_status = Column(String(40), default="ACTIVE", nullable=False, index=True)
    admin_verified = Column(Boolean, default=False, nullable=False)
    admin_verified_at = Column(DateTime(timezone=True), nullable=True)
    admin_verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deactivation_reason = Column(String(500), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    reset_password_token = Column(String(255), nullable=True)
    reset_password_expires_at = Column(DateTime(timezone=True), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    email_verification_token = Column(String(255), nullable=True)
    email_verification_expires_at = Column(DateTime(timezone=True), nullable=True)
    token_version = Column(Integer, default=0, nullable=False)
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    two_factor_secret = Column(String(255), nullable=True)
    force_password_reset = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    role = relationship("Role", back_populates="users")
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    status_history = relationship(
        "UserStatusHistory",
        foreign_keys="UserStatusHistory.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    customers = relationship(
        "Customer",
        foreign_keys=[Customer.user_id],
        back_populates="user",
        cascade="all, delete-orphan",
    )
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserStatusHistory(Base):
    __tablename__ = "user_status_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    from_status = Column(String(40), nullable=True)
    to_status = Column(String(40), nullable=False, index=True)
    reason = Column(String(500), nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="status_history")


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role")


