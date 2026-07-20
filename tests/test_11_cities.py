"""Module 11 - Cities"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique

_CREATED_ID = None


def test_cities_list(headers):
    resp = requests.get(f"{BASE_URL}/cities", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_cities_list_is_array(headers):
    resp = requests.get(f"{BASE_URL}/cities", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    assert isinstance(items, list)


def test_city_detail(headers):
    resp = requests.get(f"{BASE_URL}/cities", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    if not items:
        pytest.skip("No cities in DB")
    cid = items[0]["id"]
    resp2 = requests.get(f"{BASE_URL}/cities/{cid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


@skip_if_readonly()
def test_create_city(headers, first_country_id):
    global _CREATED_ID
    payload = {
        "city_name": unique("TestCity"),
        "country_id": first_country_id,
    }
    resp = requests.post(f"{BASE_URL}/cities", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    city = body.get("data", body)
    _CREATED_ID = city.get("id")
    assert _CREATED_ID


@skip_if_readonly()
def test_create_city_without_country_fails(headers):
    resp = requests.post(f"{BASE_URL}/cities", headers=headers, json={
        "city_name": unique("TestCity"),
    }, timeout=10)
    assert resp.status_code in (400, 422)


@skip_if_readonly()
def test_update_city(headers):
    if not _CREATED_ID:
        pytest.skip("No city created to update")
    resp = requests.put(f"{BASE_URL}/cities/{_CREATED_ID}", headers=headers,
                        json={"city_name": unique("Updated"), "country_id": 1}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_disable_city(headers):
    if not _CREATED_ID:
        pytest.skip("No city created to disable")
    resp = requests.patch(f"{BASE_URL}/cities/{_CREATED_ID}/status", headers=headers,
                          json={"status": "inactive"}, timeout=10)
    assert resp.status_code in (200, 201, 204)
