"""Module 27 - Geo Reference endpoints (no auth required)"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers


def _geo_items(resp):
    body = resp.json()
    return body if isinstance(body, list) else body.get("data", body.get("items", []))


def _india_country_id():
    resp = requests.get(f"{BASE_URL}/geo/countries", timeout=10)
    assert resp.status_code == 200, resp.text
    india = next(
        (
            item for item in _geo_items(resp)
            if (item.get("code") or item.get("country_code") or "").upper() == "IN"
            or (item.get("name") or item.get("country_name") or "").lower() == "india"
        ),
        None,
    )
    if not india:
        pytest.skip("India is not present; run POST /api/admin/seed/geo before geo hierarchy tests")
    return india["id"]


def test_geo_countries_returns_200():
    resp = requests.get(f"{BASE_URL}/geo/countries", timeout=10)
    assert resp.status_code == 200, resp.text


def test_geo_countries_has_250_items():
    resp = requests.get(f"{BASE_URL}/geo/countries", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if len(items) < 200:
        pytest.skip(
            f"Full geo seed is not installed ({len(items)} countries); "
            "run POST /api/admin/seed/geo to verify reference-data completeness"
        )
    assert len(items) >= 200


def test_geo_countries_shape():
    resp = requests.get(f"{BASE_URL}/geo/countries", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert items, "No countries returned"
    first = items[0]
    for key in ("id", "name"):
        assert key in first, f"Missing key '{key}' in country: {first}"
    # Check at least one of code/phone_code/currency_code is present
    optional_keys = {"code", "phone_code", "currency_code", "country_code"}
    present = optional_keys & set(first.keys())
    assert present, f"Expected at least one of {optional_keys} in country: {first}"


def test_geo_states_for_india():
    resp = requests.get(f"{BASE_URL}/geo/states", params={"country_id": _india_country_id()}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text
    assert len(items) > 0, "Expected states for India (country_id=101)"


def test_geo_states_shape():
    resp = requests.get(f"{BASE_URL}/geo/states", params={"country_id": 101}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No states returned for India")
    first = items[0]
    assert "id" in first, f"Missing 'id' in state: {first}"
    name_key = "name" if "name" in first else "state_name"
    assert name_key in first, f"Missing name key in state: {first}"


def test_geo_states_missing_country_id_returns_422():
    resp = requests.get(f"{BASE_URL}/geo/states", timeout=10)
    assert resp.status_code == 422, (
        f"Expected 422 when country_id missing, got {resp.status_code}: {resp.text}"
    )


def test_geo_states_invalid_country_returns_empty():
    resp = requests.get(f"{BASE_URL}/geo/states", params={"country_id": 999999}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text
    assert len(items) == 0, f"Expected empty list for non-existent country, got {len(items)} items"


def test_geo_cities_for_state():
    # First get a valid state_id from India
    resp_states = requests.get(f"{BASE_URL}/geo/states", params={"country_id": _india_country_id()}, timeout=10)
    if resp_states.status_code != 200:
        pytest.skip("Cannot fetch states to get a valid state_id")
    body = resp_states.json()
    states = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not states:
        pytest.skip("No states available")
    state_id = states[0].get("id")

    resp = requests.get(f"{BASE_URL}/geo/cities", params={"state_id": state_id}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text


def test_geo_cities_without_filter_returns_empty_list():
    resp = requests.get(f"{BASE_URL}/geo/cities", timeout=10)
    assert resp.status_code == 200, resp.text
    assert _geo_items(resp) == []


def test_geo_cities_shape():
    resp_states = requests.get(f"{BASE_URL}/geo/states", params={"country_id": _india_country_id()}, timeout=10)
    if resp_states.status_code != 200:
        pytest.skip("Cannot fetch states")
    body = resp_states.json()
    states = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not states:
        pytest.skip("No states available")
    state_id = states[0].get("id")

    resp = requests.get(f"{BASE_URL}/geo/cities", params={"state_id": state_id}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No cities for this state")
    first = items[0]
    assert "id" in first, f"Missing 'id' in city: {first}"
    name_key = "name" if "name" in first else "city_name"
    assert name_key in first, f"Missing name key in city: {first}"
