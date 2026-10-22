import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.reports import ReportScheduleCreate, _period_params


@pytest.mark.parametrize(
    ("period", "start_date", "end_date"),
    [
        ("custom", "", ""),
        ("custom", "2026-10-01", ""),
        ("custom", "2026-10-03", "2026-10-01"),
        ("custom", "not-a-date", "2026-10-01"),
    ],
)
def test_custom_report_period_rejects_incomplete_or_invalid_ranges(period, start_date, end_date):
    with pytest.raises(HTTPException) as error:
        _period_params(period, start_date, end_date)
    assert error.value.status_code == 400


def test_custom_report_period_accepts_complete_range():
    params = _period_params("custom", "2026-10-01", "2026-10-31")
    assert params["period"] == "custom"
    assert params["start"] < params["end"]


def test_report_schedule_validates_cadence_and_recipients():
    schedule = ReportScheduleCreate(
        report_type=" summary ",
        cadence="WEEKLY",
        recipient_emails="OPS@example.com, finance@example.com",
    )
    assert schedule.report_type == "summary"
    assert schedule.cadence == "weekly"
    assert schedule.recipient_emails == "ops@example.com, finance@example.com"

    with pytest.raises(ValidationError):
        ReportScheduleCreate(report_type="summary", cadence="hourly", recipient_emails="ops@example.com")
    with pytest.raises(ValidationError):
        ReportScheduleCreate(report_type="summary", recipient_emails="not-an-email")
