"""Module 16 — Tour Pricing"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly

_PRICING_ID = None
_ACTIVITY_ID = None
_EXTRA_ID = None


def test_pricing_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/pricing", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_optional_activities_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/optional-activities", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_accommodation_extras_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/accommodation-extras", headers=headers, timeout=10)
    assert resp.status_code == 200


# ── Pricing Slabs ─────────────────────────────────────────────────────────────

@skip_if_readonly()
def test_create_pricing_slab(headers, first_tour_id):
    global _PRICING_ID
    payload = {
        "passenger_from": 1,
        "passenger_to": 4,
        "adult_price": 250.0,
        "child_price": 150.0,
        "supplier_price": 180.0,
        "markup_type": "percentage",
        "markup_value": 20.0,
        "final_price": 300.0,
        "currency": "USD",
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/pricing", headers=headers,
                         json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _PRICING_ID = item.get("id")
    assert _PRICING_ID


@skip_if_readonly()
def test_update_pricing_slab(headers, first_tour_id):
    if not _PRICING_ID:
        pytest.skip("No pricing slab created")
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/pricing/{_PRICING_ID}",
                        headers=headers, json={"adult_price": 275.0, "final_price": 330.0,
                                               "passenger_from": 1, "passenger_to": 4,
                                               "markup_type": "percentage", "markup_value": 20.0,
                                               "currency": "USD"}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_delete_pricing_slab(headers, first_tour_id):
    if not _PRICING_ID:
        pytest.skip("No pricing slab created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/pricing/{_PRICING_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)


# ── Optional Activities ───────────────────────────────────────────────────────

@skip_if_readonly()
def test_create_optional_activity(headers, first_tour_id):
    global _ACTIVITY_ID
    payload = {
        "activity_name": "Desert Safari",
        "description": "Evening desert safari",
        "price_per_person": 75.0,
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/optional-activities",
                         headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _ACTIVITY_ID = item.get("id")
    assert _ACTIVITY_ID


@skip_if_readonly()
def test_update_optional_activity(headers, first_tour_id):
    if not _ACTIVITY_ID:
        pytest.skip("No activity created")
    resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/optional-activities/{_ACTIVITY_ID}",
                        headers=headers, json={"activity_name": "Updated Safari",
                                               "price_per_person": 85.0}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_delete_optional_activity(headers, first_tour_id):
    if not _ACTIVITY_ID:
        pytest.skip("No activity created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/optional-activities/{_ACTIVITY_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)


# ── Accommodation Extras ──────────────────────────────────────────────────────

@skip_if_readonly()
def test_create_accommodation_extra(headers, first_tour_id):
    global _EXTRA_ID
    payload = {
        "accommodation_name": "Sea View Room",
        "description": "Upgraded sea view",
        "extra_price": 50.0,
        "price_type": "per_person",
        "is_default": False,
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/accommodation-extras",
                         headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _EXTRA_ID = item.get("id")
    assert _EXTRA_ID


@skip_if_readonly()
def test_delete_accommodation_extra(headers, first_tour_id):
    if not _EXTRA_ID:
        pytest.skip("No extra created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/accommodation-extras/{_EXTRA_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)
