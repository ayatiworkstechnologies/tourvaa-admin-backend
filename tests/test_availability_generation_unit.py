"""Pure unit tests for the recurring-availability expansion (no server needed)."""
from datetime import date

import pytest

import app.main  # noqa: F401 - registers every model before mapper configuration
from app.schemas.tours import AvailabilityConfigPayload
from app.services.tour_availability import _generate_dates

START, END = date(2026, 10, 1), date(2026, 12, 31)
SAT, FRI = 5, 4


def iso(days):
    return [d.isoformat() for d in days]


def test_fortnightly_week_one_and_two_alternate():
    assert iso(_generate_dates(START, END, "fortnightly", 1, {SAT}))[:3] == ["2026-10-03", "2026-10-17", "2026-10-31"]
    assert iso(_generate_dates(START, END, "fortnightly", 2, {SAT}))[:3] == ["2026-10-10", "2026-10-24", "2026-11-07"]


def test_monthly_first_and_third_saturday():
    assert iso(_generate_dates(START, END, "monthly", None, {SAT}, [1, 3])) == [
        "2026-10-03", "2026-10-17", "2026-11-07", "2026-11-21", "2026-12-05", "2026-12-19",
    ]


def test_monthly_last_friday():
    assert iso(_generate_dates(START, END, "monthly", None, {FRI}, [5])) == ["2026-10-30", "2026-11-27", "2026-12-25"]


def test_monthly_falls_back_to_single_frequency_week_for_older_data():
    assert iso(_generate_dates(START, END, "monthly", 2, {0}, None)) == ["2026-10-12", "2026-11-09", "2026-12-14"]


def test_payload_accepts_legacy_single_week_and_requires_a_week_for_monthly():
    legacy = AvailabilityConfigPayload(frequency="monthly", frequency_week=2, frequency_days=[0])
    assert legacy.frequency_weeks == [2]
    multi = AvailabilityConfigPayload(frequency="monthly", frequency_weeks=[5, 1], frequency_days=[0])
    assert multi.frequency_weeks == [1, 5] and multi.frequency_week == 1
    with pytest.raises(ValueError):
        AvailabilityConfigPayload(frequency="monthly", frequency_days=[0])
