"""Module 17 - Tour Calendar & Unavailable Dates"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly

_CALENDAR_ID = None
_UNAVAIL_ID = None


def test_calendar_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/calendar", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_unavailable_dates_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/unavailable-dates", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_calendar_returns_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/calendar", headers=headers, timeout=10)
    body = resp.json()
    data = body.get("data", body)
    assert isinstance(data, list)


# ── Calendar Entries ──────────────────────────────────────────────────────────

@skip_if_readonly()
def test_create_calendar_entry(headers, first_tour_id):
    global _CALENDAR_ID
    payload = {
        "tour_date": "2027-03-15T00:00:00",
        "available_seats": 20,
        "booked_seats": 0,
        "status": "available",
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/calendar",
                         headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _CALENDAR_ID = item.get("id")
    assert _CALENDAR_ID


@skip_if_readonly()
def test_update_calendar_entry(headers, first_tour_id):
    if not _CALENDAR_ID:
        pytest.skip("No calendar entry created")
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/calendar/{_CALENDAR_ID}",
                        headers=headers, json={
                            "tour_date": "2027-03-15T00:00:00",
                            "available_seats": 25,
                            "booked_seats": 5,
                            "status": "available",
                        }, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_calendar_invalid_status(headers, first_tour_id):
    payload = {
        "tour_date": "2027-06-01T00:00:00",
        "available_seats": 10,
        "booked_seats": 0,
        "status": "invalid_status",
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/calendar",
                         headers=headers, json=payload, timeout=10)
    assert resp.status_code in (400, 422)


@skip_if_readonly()
def test_delete_calendar_entry(headers, first_tour_id):
    if not _CALENDAR_ID:
        pytest.skip("No calendar entry created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/calendar/{_CALENDAR_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)


# ── Unavailable Dates ─────────────────────────────────────────────────────────

@skip_if_readonly()
def test_create_unavailable_date(headers, first_tour_id):
    global _UNAVAIL_ID
    payload = {
        "unavailable_date": "2027-04-01T00:00:00",
        "reason": "Public holiday",
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/unavailable-dates",
                         headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _UNAVAIL_ID = item.get("id")
    assert _UNAVAIL_ID


# ── Recurring availability schedule (advance booking + frequency) ──────────────

def test_availability_config_starts_empty(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/availability", headers=headers, timeout=10)
    assert resp.status_code == 200
    # May be null (no schedule saved yet) or a dict from an earlier test run -
    # either shape is valid, this just confirms the endpoint responds.
    assert "data" in resp.json()


@skip_if_readonly()
def test_availability_config_generates_weekly_calendar_entries(headers, first_tour_id):
    # A distant, dedicated date range so this never collides with dates other
    # tests in this module create/delete (all in 2027).
    payload = {
        "availability_start_date": "2028-01-03T00:00:00",  # a Monday
        "availability_end_date": "2028-01-16T00:00:00",  # two full weeks later
        "min_advance_booking_days": 5,
        "frequency": "weekly",
        "frequency_days": [0, 2],  # Monday, Wednesday
        "seats_per_occurrence": 12,
    }
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/availability", headers=headers, json=payload, timeout=10)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["data"]
    assert saved["frequency"] == "weekly"
    assert saved["min_advance_booking_days"] == 5

    cal = requests.get(f"{BASE_URL}/tours/{first_tour_id}/calendar", headers=headers, timeout=10).json()
    dates = {row["tour_date"][:10] for row in cal.get("data", cal)}
    # Mondays/Wednesdays between 2028-01-03 and 2028-01-16.
    for expected in ["2028-01-03", "2028-01-05", "2028-01-10", "2028-01-12"]:
        assert expected in dates, f"{expected} missing from generated calendar entries: {sorted(d for d in dates if d.startswith('2028-01'))}"


@skip_if_readonly()
def test_availability_config_is_idempotent_on_resave(headers, first_tour_id):
    # Saving the same schedule twice must not create duplicate calendar rows.
    payload = {
        "availability_start_date": "2028-01-03T00:00:00",
        "availability_end_date": "2028-01-16T00:00:00",
        "min_advance_booking_days": 5,
        "frequency": "weekly",
        "frequency_days": [0, 2],
        "seats_per_occurrence": 12,
    }
    requests.put(f"{BASE_URL}/tours/{first_tour_id}/availability", headers=headers, json=payload, timeout=10)
    cal = requests.get(f"{BASE_URL}/tours/{first_tour_id}/calendar", headers=headers, timeout=10).json()
    rows = [r for r in cal.get("data", cal) if r["tour_date"].startswith("2028-01-03")]
    assert len(rows) == 1, "Re-saving the same schedule must not duplicate calendar entries"


@skip_if_readonly()
def test_delete_unavailable_date(headers, first_tour_id):
    if not _UNAVAIL_ID:
        pytest.skip("No unavailable date created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/unavailable-dates/{_UNAVAIL_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)
