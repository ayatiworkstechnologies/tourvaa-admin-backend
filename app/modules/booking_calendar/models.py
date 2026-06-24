from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class BookingCalendarEvent(Base):
    """Tracks calendar events created for confirmed bookings."""
    __tablename__ = "booking_calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True, index=True)

    # Calendar provider: internal, google, icalendar
    provider = Column(String(30), default="internal", nullable=False)
    # External event ID returned by the calendar provider
    external_event_id = Column(String(255), nullable=True)
    # URL to view/edit the event
    event_url = Column(String(500), nullable=True)

    # iCalendar UID for .ics file generation
    ical_uid = Column(String(100), nullable=True, index=True)
    # .ics file path stored in /storage/calendars/
    ics_file_path = Column(String(255), nullable=True)

    sync_status = Column(String(30), default="synced", nullable=False, index=True)
    # synced, failed, pending_retry
    sync_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    booking = relationship("Booking")
