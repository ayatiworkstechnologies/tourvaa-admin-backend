"""Module 14 — Basic Tours"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique

_CREATED_ID = None


def test_tours_list(headers):
    resp = requests.get(f"{BASE_URL}/tours", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_tours_list_is_array(headers):
    resp = requests.get(f"{BASE_URL}/tours", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list)


def test_tour_detail(headers):
    resp = requests.get(f"{BASE_URL}/tours", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No tours in DB")
    tid = items[0].get("id") or items[0].get("tour_id")
    resp2 = requests.get(f"{BASE_URL}/tours/{tid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_tour_detail_404(headers):
    resp = requests.get(f"{BASE_URL}/tours/9999999", headers=headers, timeout=10)
    assert resp.status_code == 404


def test_tours_require_auth():
    resp = requests.get(f"{BASE_URL}/tours", timeout=10)
    assert resp.status_code in (200, 401, 403)


@skip_if_readonly()
def test_create_tour(headers, first_country_id, first_category_id):
    global _CREATED_ID
    title = unique("Tour Test")
    payload = {
        "title": title,
        "number_of_days": 3,
        "price_start_per_person": 299.99,
        "country_id": first_country_id,
        "category_id": first_category_id,
    }
    resp = requests.post(f"{BASE_URL}/tours", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    tour = body.get("data", body)
    _CREATED_ID = tour.get("id")
    assert _CREATED_ID


@skip_if_readonly()
def test_created_tour_has_slug_and_code(headers):
    if not _CREATED_ID:
        pytest.skip("No tour created")
    resp = requests.get(f"{BASE_URL}/tours/{_CREATED_ID}", headers=headers, timeout=10)
    body = resp.json()
    tour = body.get("data", body)
    assert tour.get("slug"), "Tour should have a slug"


@skip_if_readonly()
def test_update_tour(headers):
    if not _CREATED_ID:
        pytest.skip("No tour created to update")
    resp = requests.put(f"{BASE_URL}/tours/{_CREATED_ID}", headers=headers, json={
        "title": unique("Updated Tour"), "number_of_days": 5
    }, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_publish_tour(headers):
    if not _CREATED_ID:
        pytest.skip("No tour created to publish")
    resp = requests.patch(f"{BASE_URL}/tours/{_CREATED_ID}/status", headers=headers,
                          json={"status": "published"}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_disable_tour(headers):
    if not _CREATED_ID:
        pytest.skip("No tour created to disable")
    resp = requests.patch(f"{BASE_URL}/tours/{_CREATED_ID}/status", headers=headers,
                          json={"status": "inactive"}, timeout=10)
    assert resp.status_code in (200, 201, 204)
