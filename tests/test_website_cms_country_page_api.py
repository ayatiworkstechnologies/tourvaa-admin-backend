"""HTTP contract coverage for Country Pages CMS.

These tests intentionally use the project's configured integration server and
skip writes on read-only deployments, consistent with the rest of module 33.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from tests.conftest import BASE_URL, skip_if_readonly


def _items(response):
    body = response.json()
    return body.get("items") or body.get("data", {}).get("items") or []


def _available_country_id(headers):
    countries = _items(requests.get(f"{BASE_URL}/countries?page=1&limit=1000", headers=headers, timeout=10))
    pages = _items(requests.get(f"{BASE_URL}/cms/country-pages?page=1&limit=1000", headers=headers, timeout=10))
    used = {int(row["country_id"]) for row in pages}
    return next((int(country["id"]) for country in countries if int(country["id"]) not in used), None)


def _payload(country_id):
    return {"country_id": country_id, "hero_title": "API country page", "is_active": True}


def test_country_pages_requires_cms_view_permission_when_unfiltered():
    response = requests.get(f"{BASE_URL}/cms/country-pages", timeout=10)
    assert response.status_code in (401, 403)


def test_active_country_pages_are_public_and_never_return_inactive_rows():
    response = requests.get(f"{BASE_URL}/cms/country-pages?active_only=true", timeout=10)
    assert response.status_code == 200, response.text
    assert all(row.get("is_active") is True for row in _items(response))


@skip_if_readonly()
def test_country_page_crud_validation_and_duplicate_race(headers):
    country_id = _available_country_id(headers)
    if country_id is None:
        pytest.skip("Every country already has a Country Page")

    # Invalid field lengths are rejected at the API boundary, before a DB error.
    invalid = requests.post(
        f"{BASE_URL}/cms/country-pages", headers=headers,
        json={**_payload(country_id), "hero_title": "x" * 201}, timeout=10,
    )
    assert invalid.status_code == 422, invalid.text

    def create():
        return requests.post(f"{BASE_URL}/cms/country-pages", headers=headers, json=_payload(country_id), timeout=20)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 400]
    created = next(response.json()["data"] for response in responses if response.status_code == 200)
    try:
        listed = requests.get(f"{BASE_URL}/cms/country-pages?page=1&limit=1000", headers=headers, timeout=10)
        assert listed.status_code == 200, listed.text
        assert any(row["id"] == created["id"] for row in _items(listed))

        updated = requests.put(
            f"{BASE_URL}/cms/country-pages/{created['id']}", headers=headers,
            json={**_payload(country_id), "hero_title": "Updated API country page", "is_active": False}, timeout=10,
        )
        assert updated.status_code == 200, updated.text
        public = requests.get(f"{BASE_URL}/public/country-pages", timeout=10)
        assert public.status_code == 200, public.text
        assert all(row["id"] != created["id"] for row in _items(public))
    finally:
        deleted = requests.delete(f"{BASE_URL}/cms/country-pages/{created['id']}", headers=headers, timeout=10)
        assert deleted.status_code == 200, deleted.text
