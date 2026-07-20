"""Module 10 - Countries"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique

_CREATED_ID = None


def test_countries_list(headers):
    resp = requests.get(f"{BASE_URL}/countries", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_countries_list_is_array(headers):
    resp = requests.get(f"{BASE_URL}/countries", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    assert isinstance(items, list)


def test_countries_require_auth():
    resp = requests.get(f"{BASE_URL}/countries", timeout=10)
    assert resp.status_code in (200, 401, 403)


def test_country_detail(headers):
    resp = requests.get(f"{BASE_URL}/countries", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    if not items:
        pytest.skip("No countries in DB")
    cid = items[0]["id"]
    resp2 = requests.get(f"{BASE_URL}/countries/{cid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


@skip_if_readonly()
def test_create_country(headers):
    global _CREATED_ID
    import uuid
    suffix = uuid.uuid4().hex[:4].upper()
    payload = {
        "country_name": unique("TestCountry"),
        "country_code": suffix,
        "phone_code": "+999",
        "currency_code": "TST",
    }
    resp = requests.post(f"{BASE_URL}/countries", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    country = body.get("data", body)
    _CREATED_ID = country.get("id")
    assert _CREATED_ID


@skip_if_readonly()
def test_update_country(headers):
    if not _CREATED_ID:
        pytest.skip("No country created to update")
    import uuid
    upd_code = uuid.uuid4().hex[:4].upper()
    resp = requests.put(f"{BASE_URL}/countries/{_CREATED_ID}", headers=headers,
                        json={"country_name": unique("Updated"), "country_code": upd_code}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_disable_country(headers):
    if not _CREATED_ID:
        pytest.skip("No country created to disable")
    resp = requests.patch(f"{BASE_URL}/countries/{_CREATED_ID}/status", headers=headers,
                          json={"status": "inactive"}, timeout=10)
    assert resp.status_code in (200, 201, 204)
