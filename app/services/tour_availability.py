"""Recurring tour-availability schedule: a Tour Start/End Date range, a
minimum-advance-booking window, and a Weekly/Fortnightly/Monthly frequency
that expands into concrete TourCalendar rows (see _generate_dates below).

Also owns the "tour ending soon" reminder email swept by
app.main._tour_availability_reminder_loop, mirroring the stage/dedup pattern
in app.services.invoices.check_balance_due_reminders.
"""
import calendar as calendar_module
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models.cms import Tour
from app.models.suppliers import Supplier
from app.models.tours import TourAvailabilityConfig, TourCalendar
from app.models.users import User
from app.schemas.tours import AvailabilityConfigPayload
from app.services.audit import log_audit
from app.services.tour_versions import maybe_resubmit_for_review

logger = logging.getLogger(__name__)

_END_DATE_REMINDER_WINDOW_DAYS = 30
_END_DATE_REMINDER_RESEND_INTERVAL = timedelta(days=7)


def _require_tour(db: Session, tour_id: int) -> Tour:
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    return tour


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _ser_config(o: TourAvailabilityConfig) -> dict:
    return {
        "id": o.id, "tour_id": o.tour_id,
        "availability_start_date": o.availability_start_date,
        "availability_end_date": o.availability_end_date,
        "min_advance_booking_days": o.min_advance_booking_days,
        "frequency": o.frequency,
        "frequency_week": o.frequency_week,
        "frequency_days": o.frequency_days or [],
        "seats_per_occurrence": o.seats_per_occurrence,
        "created_at": o.created_at, "updated_at": o.updated_at,
    }


def get_availability_config(db: Session, tour_id: int) -> dict | None:
    _require_tour(db, tour_id)
    o = db.query(TourAvailabilityConfig).filter(TourAvailabilityConfig.tour_id == tour_id).first()
    return _ser_config(o) if o else None


def _generate_dates(start: date, end: date, frequency: str, frequency_week: int | None, weekdays: set[int]) -> list[date]:
    """weekdays uses Python's date.weekday() convention: 0=Monday..6=Sunday."""
    dates: list[date] = []

    if frequency == "weekly":
        cursor = start
        while cursor <= end:
            if cursor.weekday() in weekdays:
                dates.append(cursor)
            cursor += timedelta(days=1)

    elif frequency == "fortnightly":
        anchor_monday = start - timedelta(days=start.weekday())
        week_offset = 0 if (frequency_week or 1) == 1 else 1
        week_start = anchor_monday + timedelta(weeks=week_offset)
        while week_start <= end:
            for weekday in weekdays:
                candidate = week_start + timedelta(days=weekday)
                if start <= candidate <= end:
                    dates.append(candidate)
            week_start += timedelta(weeks=2)

    elif frequency == "monthly":
        nth = frequency_week or 1
        month_cursor = date(start.year, start.month, 1)
        while month_cursor <= end:
            days_in_month = calendar_module.monthrange(month_cursor.year, month_cursor.month)[1]
            first_weekday = month_cursor.weekday()
            for weekday in weekdays:
                day_number = 1 + ((weekday - first_weekday) % 7) + (nth - 1) * 7
                if day_number <= days_in_month:
                    candidate = date(month_cursor.year, month_cursor.month, day_number)
                    if start <= candidate <= end:
                        dates.append(candidate)
            month_cursor = date(month_cursor.year + 1, 1, 1) if month_cursor.month == 12 else date(month_cursor.year, month_cursor.month + 1, 1)

    return sorted(set(dates))


def save_availability_config(db: Session, tour_id: int, data: AvailabilityConfigPayload, actor: User, request: Request | None = None) -> dict:
    _require_tour(db, tour_id)
    o = db.query(TourAvailabilityConfig).filter(TourAvailabilityConfig.tour_id == tour_id).first()
    is_new = o is None
    if is_new:
        o = TourAvailabilityConfig(tour_id=tour_id)
        db.add(o)

    o.availability_start_date = data.availability_start_date
    o.availability_end_date = data.availability_end_date
    o.min_advance_booking_days = data.min_advance_booking_days
    o.frequency = data.frequency
    o.frequency_week = data.frequency_week
    o.frequency_days = data.frequency_days
    o.seats_per_occurrence = data.seats_per_occurrence

    created_count = 0
    start = _as_date(o.availability_start_date)
    end = _as_date(o.availability_end_date)
    if o.frequency and o.frequency_days and start and end:
        candidate_dates = _generate_dates(start, end, o.frequency, o.frequency_week, set(o.frequency_days))
        existing_dates = {
            _as_date(d) for (d,) in db.query(TourCalendar.tour_date).filter(TourCalendar.tour_id == tour_id).all()
        }
        # Only ever ADD missing generated dates - never delete or overwrite
        # an existing entry (it may already have real bookings against it).
        for candidate in candidate_dates:
            if candidate in existing_dates:
                continue
            entry_dt = datetime.combine(candidate, datetime.min.time())
            db.add(TourCalendar(
                tour_id=tour_id, tour_date=entry_dt, start_date=entry_dt, end_date=entry_dt,
                available_seats=o.seats_per_occurrence, booked_seats=0, status="available",
            ))
            created_count += 1

    log_audit(
        db, actor=actor, action="save_availability_config", entity_type="tour", entity_id=tour_id,
        new_values={
            "availability_start_date": str(o.availability_start_date) if o.availability_start_date else None,
            "availability_end_date": str(o.availability_end_date) if o.availability_end_date else None,
            "min_advance_booking_days": o.min_advance_booking_days,
            "frequency": o.frequency, "frequency_week": o.frequency_week, "frequency_days": o.frequency_days,
            "calendar_entries_generated": created_count,
        },
        request=request,
    )
    maybe_resubmit_for_review(db, tour_id, actor)
    db.commit()
    db.refresh(o)
    return _ser_config(o)


def min_advance_booking_days(db: Session, tour_id: int) -> int:
    o = db.query(TourAvailabilityConfig).filter(TourAvailabilityConfig.tour_id == tour_id).first()
    return o.min_advance_booking_days if o else 0


def assert_meets_advance_booking_window(db: Session, tour_id: int, tour_date: datetime | date) -> None:
    days = min_advance_booking_days(db, tour_id)
    if days <= 0:
        return
    earliest_bookable = date.today() + timedelta(days=days)
    if _as_date(tour_date) < earliest_bookable:
        raise HTTPException(
            status_code=400,
            detail=f"This tour requires booking at least {days} day(s) in advance - the earliest bookable date is {earliest_bookable.isoformat()}.",
        )


def check_availability_end_date_reminders(db: Session) -> None:
    """Hourly sweep (app.main._tour_availability_reminder_loop): email the
    supplier + admin once a tour's availability window is within 30 days of
    its end date, suggesting they extend it. Resent at most weekly."""
    from app.utils.mailer import try_send_email

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=_END_DATE_REMINDER_WINDOW_DAYS)

    configs = (
        db.query(TourAvailabilityConfig)
        .filter(
            TourAvailabilityConfig.availability_end_date.isnot(None),
            TourAvailabilityConfig.availability_end_date <= window_end,
            TourAvailabilityConfig.availability_end_date >= now,
        )
        .all()
    )

    for config in configs:
        if config.last_end_date_reminder_at and (now - config.last_end_date_reminder_at) < _END_DATE_REMINDER_RESEND_INTERVAL:
            continue
        try:
            tour = db.query(Tour).filter(Tour.id == config.tour_id).first()
            if not tour:
                continue
            end_date_str = config.availability_end_date.date().isoformat()
            recipients = []
            if tour.supplier_id:
                supplier = db.query(Supplier).filter(Supplier.id == tour.supplier_id).first()
                if supplier and supplier.contacts:
                    primary = next((c for c in supplier.contacts if c.is_primary), supplier.contacts[0])
                    if primary and primary.email:
                        recipients.append(primary.email)
            from app.models.settings import AppSetting
            from app.services.settings import sanitize_public_contact_setting
            setting = db.query(AppSetting).filter(AppSetting.key == "support_email").first()
            admin_email = sanitize_public_contact_setting("support_email", setting.value if setting else "")
            if admin_email:
                recipients.append(admin_email)

            subject = f"Tour availability ending soon - {tour.title}"
            body = (
                f"<p><strong>{tour.title}</strong> is available for booking through <strong>{end_date_str}</strong>, "
                f"which is within the next {_END_DATE_REMINDER_WINDOW_DAYS} days.</p>"
                f"<p>Extend the Tour End Date in the tour's Calendar tab if you'd like to keep taking bookings beyond that date.</p>"
            )
            for recipient in recipients:
                try_send_email(recipient, subject, body, template_key="tour_availability_ending_soon")

            config.last_end_date_reminder_at = now
            db.commit()
        except Exception:
            logger.exception("Failed to send availability end-date reminder for tour_id=%s", config.tour_id)
            db.rollback()
