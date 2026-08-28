"""Module 18 - Tour Discounts"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique

_DISCOUNT_ID = None


def test_discounts_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/discounts", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_discounts_returns_list(headers, first_tour_id):
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/discounts", headers=headers, timeout=10)
    body = resp.json()
    data = body.get("data", body)
    assert isinstance(data, list)


def test_discounts_invalid_tour(headers):
    resp = requests.get(f"{BASE_URL}/tours/9999999/discounts", headers=headers, timeout=10)
    assert resp.status_code == 404


@skip_if_readonly()
def test_create_discount(headers, first_tour_id):
    global _DISCOUNT_ID
    payload = {
        "discount_name": unique("EarlyBird"),
        "discount_type": "percentage",
        "discount_value": 10.0,
        "valid_from": "2027-01-01T00:00:00",
        "valid_to": "2027-12-31T23:59:59",
        "min_pax": 2,
        "is_active": True,
    }
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/discounts",
                         headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    item = body.get("data", body)
    _DISCOUNT_ID = item.get("id")
    assert _DISCOUNT_ID


@skip_if_readonly()
def test_discount_validation_missing_required(headers, first_tour_id):
    # Missing discount_name and discount_type should fail validation
    resp = requests.post(f"{BASE_URL}/tours/{first_tour_id}/discounts",
                         headers=headers, json={"discount_value": 10.0}, timeout=10)
    assert resp.status_code in (400, 422), resp.text


@skip_if_readonly()
def test_amend_discount_changes_percentage(headers, first_tour_id):
    # Free-form Edit is removed -- only an amendment (percentage and/or a
    # later end date) is allowed, via PATCH .../amend.
    if not _DISCOUNT_ID:
        pytest.skip("No discount created")
    resp = requests.patch(f"{BASE_URL}/tours/{first_tour_id}/discounts/{_DISCOUNT_ID}/amend",
                          headers=headers, json={"new_discount_value": 15.0}, timeout=10)
    assert resp.status_code in (200, 201, 204), resp.text


@skip_if_readonly()
def test_amend_discount_requires_a_change(headers, first_tour_id):
    if not _DISCOUNT_ID:
        pytest.skip("No discount created")
    resp = requests.patch(f"{BASE_URL}/tours/{first_tour_id}/discounts/{_DISCOUNT_ID}/amend",
                          headers=headers, json={}, timeout=10)
    assert resp.status_code in (400, 422), resp.text


def test_discount_history_lists_versions(headers, first_tour_id):
    if not _DISCOUNT_ID:
        pytest.skip("No discount created")
    resp = requests.get(f"{BASE_URL}/tours/{first_tour_id}/discounts/{_DISCOUNT_ID}/history",
                        headers=headers, timeout=10)
    assert resp.status_code == 200
    data = resp.json().get("data", [])
    assert isinstance(data, list)
    assert len(data) >= 1


def test_discount_edit_and_delete_are_removed(headers, first_tour_id):
    if not _DISCOUNT_ID:
        pytest.skip("No discount created")
    put_resp = requests.put(f"{BASE_URL}/tours/{first_tour_id}/discounts/{_DISCOUNT_ID}",
                            headers=headers, json={"discount_name": "x"}, timeout=10)
    assert put_resp.status_code in (404, 405)
    delete_resp = requests.delete(f"{BASE_URL}/tours/{first_tour_id}/discounts/{_DISCOUNT_ID}",
                                  headers=headers, timeout=10)
    assert delete_resp.status_code in (404, 405)
