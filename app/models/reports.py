from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class ReportSchedule(Base):
    """A saved report-delivery configuration. Not yet auto-executed -- see
    app/routers/reports.py's schedule endpoints for the current scope
    (save/list/delete only; unattended sending requires a scheduler
    dependency that isn't part of this codebase yet)."""

    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(50), nullable=False)
    cadence = Column(String(20), nullable=False, default="weekly")
    recipient_emails = Column(String(1000), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
