"""Module 17 — Tour Calendar & Unavailable Dates"""
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


@skip_if_readonly()
def test_delete_unavailable_date(headers, first_tour_id):
    if not _UNAVAIL_ID:
        pytest.skip("No unavailable date created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/unavailable-dates/{_UNAVAIL_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)
