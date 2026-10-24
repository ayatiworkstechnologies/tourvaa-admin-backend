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

from app.config import settings
from app.models.cms import Tour
from app.models.suppliers import Supplier
from app.models.tours import TourAvailabilityConfig, TourCalendar
from app.models.users import User
from app.schemas.tours import AvailabilityConfigPayload
from app.utils.money import as_aware_utc
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
        "agent_no_deposit_buffer_weeks": o.agent_no_deposit_buffer_weeks,
        "frequency": o.frequency,
        "frequency_week": o.frequency_week,
        "frequency_weeks": o.frequency_weeks or ([o.frequency_week] if o.frequency == "monthly" and o.frequency_week else []),
        "frequency_days": o.frequency_days or [],
        "seats_per_occurrence": o.seats_per_occurrence,
        "created_at": o.created_at, "updated_at": o.updated_at,
    }


def get_availability_config(db: Session, tour_id: int) -> dict | None:
    _require_tour(db, tour_id)
    o = db.query(TourAvailabilityConfig).filter(TourAvailabilityConfig.tour_id == tour_id).first()
    return _ser_config(o) if o else None


def _generate_dates(start: date, end: date, frequency: str, frequency_week: int | None, weekdays: set[int], weeks: list[int] | None = None) -> list[date]:
    """weekdays uses Python's date.weekday() convention: 0=Monday..6=Sunday.

    fortnightly: frequency_week 1 = the week of `start`, 2 = the week after, then every 2 weeks.
    monthly: `weeks` lists which occurrence of each weekday to run - 1-4 = 1st-4th, 5 = the last
    one in the month (falls back to [frequency_week] for older data)."""
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
        nths = weeks or [frequency_week or 1]
        month_cursor = date(start.year, start.month, 1)
        while month_cursor <= end:
            days_in_month = calendar_module.monthrange(month_cursor.year, month_cursor.month)[1]
            first_weekday = month_cursor.weekday()
            last_weekday = (first_weekday + days_in_month - 1) % 7
            for weekday in weekdays:
                for nth in nths:
                    if nth == 5:  # the last such weekday of the month
                        day_number = days_in_month - ((last_weekday - weekday) % 7)
                    else:
                        day_number = 1 + ((weekday - first_weekday) % 7) + (nth - 1) * 7
                    if 1 <= day_number <= days_in_month:
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
    o.agent_no_deposit_buffer_weeks = data.agent_no_deposit_buffer_weeks
    o.frequency = data.frequency
    o.frequency_week = data.frequency_week
    o.frequency_weeks = data.frequency_weeks if data.frequency == "monthly" else []
    o.frequency_days = data.frequency_days
    o.seats_per_occurrence = data.seats_per_occurrence

    created_count = 0
    updated_count = 0
    removed_count = 0
    start = _as_date(o.availability_start_date)
    end = _as_date(o.availability_end_date)
    if o.frequency and o.frequency_days and start and end:
        candidate_dates = _generate_dates(start, end, o.frequency, o.frequency_week, set(o.frequency_days), o.frequency_weeks)
        existing_entries = {
            _as_date(c.tour_date): c for c in db.query(TourCalendar).filter(TourCalendar.tour_id == tour_id).all()
        }
        # Add missing generated dates, and update capacity for existing dates
        for candidate in candidate_dates:
            existing = existing_entries.get(candidate)
            if existing:
                if existing.status != "blocked":
                    new_seats = max(existing.booked_seats or 0, o.seats_per_occurrence)
                    if existing.available_seats != new_seats:
                        existing.available_seats = new_seats
                        if (existing.booked_seats or 0) >= new_seats and new_seats > 0:
                            existing.status = "sold_out"
                        elif existing.status == "sold_out" and new_seats > (existing.booked_seats or 0):
                            existing.status = "available"
                        updated_count += 1
                continue

            entry_dt = datetime.combine(candidate, datetime.min.time())
            db.add(TourCalendar(
                tour_id=tour_id, tour_date=entry_dt, tour_date_day=candidate, start_date=entry_dt, end_date=entry_dt,
                available_seats=o.seats_per_occurrence, booked_seats=0, status="available",
            ))
            created_count += 1

        # Changing the schedule (e.g. Monday -> Tuesday) leaves the old dates behind. On request,
        # delete future, unbooked, unblocked dates that no longer fit - never a date that any
        # booking (even a cancelled one) still points at.
        if data.remove_unmatched_dates:
            from app.models.bookings import Booking

            today = date.today()
            fitting = set(candidate_dates)
            stale = {
                d: c for d, c in existing_entries.items()
                if d not in fitting and d >= today and c.status != "blocked" and (c.booked_seats or 0) == 0
            }
            referenced = (
                {row[0] for row in db.query(Booking.tour_calendar_id).filter(Booking.tour_calendar_id.in_([c.id for c in stale.values()])).all()}
                if stale else set()
            )
            for d, c in stale.items():
                if c.id in referenced:
                    continue
                db.delete(c)
                existing_entries.pop(d, None)
                removed_count += 1

        # Also update any other unblocked calendar entries with 0 bookings for this tour
        for existing in existing_entries.values():
            if existing.status != "blocked" and (existing.booked_seats or 0) == 0:
                if existing.available_seats != o.seats_per_occurrence:
                    existing.available_seats = o.seats_per_occurrence
                    if existing.status == "sold_out" and o.seats_per_occurrence > 0:
                        existing.status = "available"
                    updated_count += 1

    log_audit(
        db, actor=actor, action="save_availability_config", entity_type="tour", entity_id=tour_id,
        new_values={
            "availability_start_date": str(o.availability_start_date) if o.availability_start_date else None,
            "availability_end_date": str(o.availability_end_date) if o.availability_end_date else None,
            "min_advance_booking_days": o.min_advance_booking_days,
            "frequency": o.frequency, "frequency_week": o.frequency_week, "frequency_days": o.frequency_days,
            "calendar_entries_generated": created_count,
            "calendar_entries_updated": updated_count,
            "calendar_entries_removed": removed_count,
        },
        request=request,
    )
    maybe_resubmit_for_review(db, tour_id, actor)
    db.commit()
    db.refresh(o)
    result = _ser_config(o)
    result["generated_dates"] = created_count
    result["removed_dates"] = removed_count
    return result


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


def deposit_balance_due_date(db: Session, tour_id: int, travel_date: datetime | date) -> tuple[date, int]:
    """The balance due date for a deposit/Reserve Now booking on this tour
    and travel date, plus the buffer weeks (X) it was derived from.

    Client rule: the due date is the start of the Xth week before the
    Minimum Advance Booking cutoff, i.e.
        cutoff_date = travel_date - min_advance_booking_days
        due_date    = cutoff_date - X weeks
    so the balance always falls due before the tour stops taking bookings.

    Independent of today's date on purpose: _deposit_window uses it to decide
    eligibility at booking time, and services.bookings._balance_due_date
    uses it afterwards (including once the date has passed, so overdue
    balances are still detected)."""
    o = db.query(TourAvailabilityConfig).filter(TourAvailabilityConfig.tour_id == tour_id).first()
    buffer_weeks = o.agent_no_deposit_buffer_weeks if o else 4
    advance_days = o.min_advance_booking_days if o else 0
    cutoff_date = _as_date(travel_date) - timedelta(days=advance_days or 0)
    return cutoff_date - timedelta(weeks=buffer_weeks), buffer_weeks


def _deposit_window(db: Session, tour_id: int, travel_date: datetime | date) -> dict:
    """Shared eligibility window for "pay a deposit now, balance later"
    across BOTH agent (Reserve Now) and customer (Secure with a Deposit)
    booking flows - one rule, not two: eligible only if today is more than
    agent_no_deposit_buffer_weeks (X) weeks before the tour's
    min-advance-booking cutoff date (travel_date - min_advance_booking_days),
    i.e. only while the balance due date (deposit_balance_due_date) is still
    in the future. The buffer-weeks/min-advance-days knobs live on
    TourAvailabilityConfig and were originally agent-only naming, but the
    client's rule is explicitly the same window for customers too (see
    agent_reserve_eligibility / customer_deposit_eligibility below, which
    customer_deposit_eligibility below. Agent Reserve Now uses the window to
    decide whether an invoice/pay-later reservation is available."""
    due_date, buffer_weeks = deposit_balance_due_date(db, tour_id, travel_date)
    eligible = due_date > date.today()
    return {"eligible": eligible, "due_date": due_date if eligible else None, "buffer_weeks": buffer_weeks}


def agent_reserve_eligibility(db: Session, tour_id: int, travel_date: datetime | date) -> dict:
    """Whether an agent may Reserve Now and be invoiced later with no deposit."""
    return _deposit_window(db, tour_id, travel_date)


def customer_deposit_eligibility(db: Session, tour_id: int, travel_date: datetime | date) -> dict:
    """Whether a customer booking this tour today may 'Secure with a
    Deposit' instead of paying in full, and on what terms - same
    eligibility window as agent_reserve_eligibility (see _deposit_window),
    paired with the tour's own customer-facing deposit terms
    (Tour.deposit_type/deposit_percentage/booking_deposit, set on the Tour
    editor's Deposit & Cancellation step)."""
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    window = _deposit_window(db, tour_id, travel_date)
    if not window["eligible"] or tour is None:
        return {**window, "deposit_type": None, "deposit_percentage": None, "booking_deposit": None}

    from app.services.settings import get_default_deposit_percentage

    deposit_type = (tour.deposit_type or "fixed")
    percentage = tour.deposit_percentage
    fixed = tour.booking_deposit
    if deposit_type != "percentage" and not fixed:
        deposit_type = "percentage"
        percentage = float(get_default_deposit_percentage(db))
    elif deposit_type == "percentage" and not percentage:
        percentage = float(get_default_deposit_percentage(db))

    return {
        **window,
        "deposit_type": deposit_type,
        "deposit_percentage": float(percentage) if percentage is not None else None,
        "booking_deposit": float(fixed) if fixed else None,
    }


def check_availability_end_date_reminders(db: Session) -> None:
    """Hourly sweep (app.main._tour_availability_reminder_loop): email the
    supplier + admin once a tour's availability window is within 30 days of
    its end date, suggesting they extend it. Resent at most weekly."""
    from app.services.notification_delivery import dispatch_lifecycle_email

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
        if config.last_end_date_reminder_at and (now - as_aware_utc(config.last_end_date_reminder_at)) < _END_DATE_REMINDER_RESEND_INTERVAL:
            continue
        try:
            tour = db.query(Tour).filter(Tour.id == config.tour_id).first()
            if not tour:
                continue
            end_date_str = config.availability_end_date.date().isoformat()
            recipients: list[tuple[str, str]] = []
            if tour.supplier_id:
                supplier = db.query(Supplier).filter(Supplier.id == tour.supplier_id).first()
                if supplier and supplier.contacts:
                    primary = next((c for c in supplier.contacts if c.is_primary), supplier.contacts[0])
                    if primary and primary.email:
                        recipients.append(("supplier", primary.email))
            from app.models.settings import AppSetting
            from app.services.settings import sanitize_public_contact_setting
            setting = db.query(AppSetting).filter(AppSetting.key == "support_email").first()
            admin_email = sanitize_public_contact_setting("support_email", setting.value if setting else "")
            if admin_email:
                recipients.append(("tourvaa_admin", admin_email))

            subject = f"Tour availability ending soon - {tour.title}"
            body = (
                f"<p><strong>{tour.title}</strong> is available for booking through <strong>{end_date_str}</strong>, "
                f"which is within the next {_END_DATE_REMINDER_WINDOW_DAYS} days.</p>"
                f"<p>Extend the Tour End Date in the tour's Calendar tab if you'd like to keep taking bookings beyond that date.</p>"
            )
            for recipient_type, recipient in recipients:
                portal_url = (
                    f"{settings.FRONTEND_URL}/supplier/tours/{tour.id}"
                    if recipient_type == "supplier"
                    else f"{settings.FRONTEND_URL}/admin/tours/{tour.id}"
                )
                dispatch_lifecycle_email(
                    db,
                    event="tour_availability_ending_soon",
                    entity_type="tour",
                    entity_id=tour.id,
                    recipient_type=recipient_type,
                    recipient_email=recipient,
                    template_key="tour_availability_ending_soon",
                    values={
                        "tour_name": tour.title,
                        "end_date": end_date_str,
                        "days": _END_DATE_REMINDER_WINDOW_DAYS,
                        "login_url": portal_url,
                        "button_text": "Review availability",
                        "button_url": portal_url,
                    },
                    fallback_subject=subject,
                    fallback_html=body,
                    event_version=now.date().isoformat(),
                )

            config.last_end_date_reminder_at = now
            db.commit()
        except Exception:
            logger.exception("Failed to send availability end-date reminder for tour_id=%s", config.tour_id)
            db.rollback()
