"""Module 16 - Tour Pricing"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly

_PRICING_ID = None


def test_pricing_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/pricing", headers=headers, timeout=10)
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
        "admin_markup_value": 10.0,
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
                                               "admin_markup_value": 12.0,
                                               "currency": "USD"}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_delete_pricing_slab(headers, first_tour_id):
    if not _PRICING_ID:
        pytest.skip("No pricing slab created")
    resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/pricing/{_PRICING_ID}",
                           headers=headers, timeout=10)
    assert resp.status_code in (200, 204)
