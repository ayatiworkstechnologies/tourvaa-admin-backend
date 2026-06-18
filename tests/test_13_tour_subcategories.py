"""Module 13 — Tour Subcategories"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique

_CREATED_ID = None


def test_subcategories_list(headers):
    resp = requests.get(f"{BASE_URL}/tour-subcategories", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_subcategory_detail(headers):
    resp = requests.get(f"{BASE_URL}/tour-subcategories", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    if not items:
        pytest.skip("No subcategories in DB")
    scid = items[0]["id"]
    resp2 = requests.get(f"{BASE_URL}/tour-subcategories/{scid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


@skip_if_readonly()
def test_create_subcategory(headers, first_category_id):
    global _CREATED_ID
    name = unique("TestSubcat")
    payload = {
        "subcategory_name": name,
        "category_id": first_category_id,
        "description": "Test sub",
    }
    resp = requests.post(f"{BASE_URL}/tour-subcategories", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    sub = body.get("data", body)
    _CREATED_ID = sub.get("id")
    assert _CREATED_ID


@skip_if_readonly()
def test_subcategory_has_slug(headers):
    if not _CREATED_ID:
        pytest.skip("No subcategory created")
    resp = requests.get(f"{BASE_URL}/tour-subcategories/{_CREATED_ID}", headers=headers, timeout=10)
    body = resp.json()
    sub = body.get("data", body)
    assert sub.get("slug"), "Subcategory should have a slug"


@skip_if_readonly()
def test_create_subcategory_without_category_fails(headers):
    resp = requests.post(f"{BASE_URL}/tour-subcategories", headers=headers, json={
        "subcategory_name": unique("NoCategory"),
    }, timeout=10)
    assert resp.status_code in (400, 422)


@skip_if_readonly()
def test_update_subcategory(headers):
    if not _CREATED_ID:
        pytest.skip("No subcategory created to update")
    resp = requests.put(f"{BASE_URL}/tour-subcategories/{_CREATED_ID}", headers=headers,
                        json={"subcategory_name": unique("Updated")}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_disable_subcategory(headers):
    if not _CREATED_ID:
        pytest.skip("No subcategory created to disable")
    resp = requests.patch(f"{BASE_URL}/tour-subcategories/{_CREATED_ID}/status", headers=headers,
                          json={"status": "inactive"}, timeout=10)
    assert resp.status_code in (200, 201, 204)
