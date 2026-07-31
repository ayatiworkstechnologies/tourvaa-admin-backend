from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class ReportSchedule(Base):
    """A saved report-delivery configuration, executed by the background
    loop in app/main.py (see app/services/reports.py:run_due_report_schedules),
    which polls for schedules due per their cadence and emails the CSV."""

    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(50), nullable=False)
    cadence = Column(String(20), nullable=False, default="weekly")
    recipient_emails = Column(String(1000), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_run_at = Column(DateTime(timezone=True), nullable=True)
