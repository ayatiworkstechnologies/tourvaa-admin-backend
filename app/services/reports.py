import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.reports import ReportSchedule
from app.models.users import User
from app.utils.mailer import try_send_email

logger = logging.getLogger(__name__)

CADENCE_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}
CADENCE_PERIODS = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
}


def _is_due(schedule: ReportSchedule, now: datetime) -> bool:
    interval = CADENCE_INTERVALS.get((schedule.cadence or "weekly").lower(), CADENCE_INTERVALS["weekly"])
    if schedule.last_run_at is None:
        return True
    last_run = schedule.last_run_at
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    return now - last_run >= interval


def _send_scheduled_report(db: Session, schedule: ReportSchedule, now: datetime):
    from app.routers.reports import REPORT_FETCHERS, REPORT_LABELS, _period_params

    if schedule.report_type not in REPORT_FETCHERS:
        logger.warning("Report schedule %s references unknown report type %s", schedule.id, schedule.report_type)
        schedule.last_run_at = now
        return

    actor = db.query(User).filter(User.id == schedule.created_by).first() if schedule.created_by else None
    period = CADENCE_PERIODS.get((schedule.cadence or "weekly").lower(), "week")
    params = _period_params(period, "", "")
    rows = REPORT_FETCHERS[schedule.report_type](db, params, actor)

    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("No data for this period\n")

    label = REPORT_LABELS.get(schedule.report_type, schedule.report_type)
    recipients = [email.strip() for email in (schedule.recipient_emails or "").split(",") if email.strip()]
    attachment = (f"{schedule.report_type}.csv", buffer.getvalue().encode("utf-8"), "csv")
    for recipient in recipients:
        try_send_email(
            recipient,
            f"Tourvaa scheduled report: {label}",
            f"<p>Your scheduled <strong>{label}</strong> report is attached as a CSV file.</p>",
            attachments=[attachment],
            template_key="scheduled_report",
        )
    schedule.last_run_at = now


def run_due_report_schedules(db: Session) -> list[int]:
    """Send every active ReportSchedule that's due per its cadence. Called
    periodically by the background loop in app/main.py."""
    now = datetime.now(timezone.utc)
    schedules = db.query(ReportSchedule).filter(ReportSchedule.is_active == True).all()  # noqa: E712
    executed: list[int] = []
    for schedule in schedules:
        if not _is_due(schedule, now):
            continue
        try:
            _send_scheduled_report(db, schedule, now)
            executed.append(schedule.id)
        except Exception:
            logger.exception("Failed to execute report schedule %s", schedule.id)
    if executed:
        db.commit()
    return executed
