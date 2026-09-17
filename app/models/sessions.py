from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(120), nullable=False, unique=True, index=True)
    # jti of the most recently issued refresh token for this session. Set on
    # login and rotated on every /auth/refresh-token call; a refresh token
    # presented with a different jti than this has already been rotated
    # (stolen/replayed), and refresh_token() in routers/auth.py revokes the
    # session on that mismatch instead of accepting it.
    current_refresh_jti = Column(String(64), nullable=True)
    ip_address = Column(String(100), nullable=True)
    user_agent = Column(String(255), nullable=True)
    status = Column(String(30), default="active", nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="sessions")


class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String(150), nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)
    failure_reason = Column(String(255), nullable=True)
    client_type = Column(String(30), default="web", nullable=False)
    device_id = Column(String(120), nullable=True)
    device_name = Column(String(180), nullable=True)
    ip_address = Column(String(100), nullable=True)
    user_agent = Column(String(255), nullable=True)
    session_id = Column(String(120), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="login_history")

