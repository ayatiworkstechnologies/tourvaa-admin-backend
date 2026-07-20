"""Module 12 - Tour Categories"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique

_CREATED_ID = None


def test_categories_list(headers):
    resp = requests.get(f"{BASE_URL}/tour-categories", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_categories_list_is_array(headers):
    resp = requests.get(f"{BASE_URL}/tour-categories", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    assert isinstance(items, list)


def test_category_detail(headers):
    resp = requests.get(f"{BASE_URL}/tour-categories", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", [])
    if not items:
        pytest.skip("No categories in DB")
    cid = items[0]["id"]
    resp2 = requests.get(f"{BASE_URL}/tour-categories/{cid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


@skip_if_readonly()
def test_create_category(headers):
    global _CREATED_ID
    name = unique("TestCat")
    payload = {"category_name": name, "description": "Test description"}
    resp = requests.post(f"{BASE_URL}/tour-categories", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    cat = body.get("data", body)
    _CREATED_ID = cat.get("id")
    assert _CREATED_ID


@skip_if_readonly()
def test_created_category_has_slug(headers):
    if not _CREATED_ID:
        pytest.skip("No category created")
    resp = requests.get(f"{BASE_URL}/tour-categories/{_CREATED_ID}", headers=headers, timeout=10)
    body = resp.json()
    cat = body.get("data", body)
    assert cat.get("slug"), "Category should have a slug"


@skip_if_readonly()
def test_update_category(headers):
    if not _CREATED_ID:
        pytest.skip("No category created to update")
    resp = requests.put(f"{BASE_URL}/tour-categories/{_CREATED_ID}", headers=headers,
                        json={"category_name": unique("UpdatedCat")}, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_disable_category(headers):
    if not _CREATED_ID:
        pytest.skip("No category created to disable")
    resp = requests.patch(f"{BASE_URL}/tour-categories/{_CREATED_ID}/status", headers=headers,
                          json={"status": "inactive"}, timeout=10)
    assert resp.status_code in (200, 201, 204)
