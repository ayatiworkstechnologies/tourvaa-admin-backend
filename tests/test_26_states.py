"""Module 26 — States CRUD"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

_created_id = None


def _india_country_id(headers):
    resp = requests.get(f"{BASE_URL}/countries", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    india = next(
        (
            item for item in items
            if (item.get("country_code") or item.get("code") or "").upper() == "IN"
            or (item.get("country_name") or item.get("name") or "").lower() == "india"
        ),
        None,
    )
    if not india:
        pytest.skip("India is not present; run POST /api/admin/seed/geo before geo completeness tests")
    return india["id"]


def test_states_list(headers):
    resp = requests.get(f"{BASE_URL}/states", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"


def test_states_list_has_items(headers):
    resp = requests.get(f"{BASE_URL}/states", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert len(items) > 0, "Expected at least some states in DB"


def test_states_filter_by_country_id(headers):
    # India country_id=101 should have 18+ states
    resp = requests.get(f"{BASE_URL}/states", headers=headers, params={"country_id": 101}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text
    if items:
        for item in items:
            cid = item.get("country_id") or item.get("country", {}).get("id")
            assert cid == 101, f"Item country_id mismatch: {item}"


def test_states_india_has_enough_states(headers):
    resp = requests.get(
        f"{BASE_URL}/states",
        headers=headers,
        params={"country_id": _india_country_id(headers)},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert len(items) >= 18, f"India should have at least 18 states, got {len(items)}"


def test_states_search_maharashtra(headers):
    resp = requests.get(f"{BASE_URL}/states", headers=headers, params={"search": "maha"}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text
    names = [
        (item.get("state_name") or item.get("name") or "").lower()
        for item in items
    ]
    assert any("maharashtra" in n for n in names), (
        f"Search for 'maha' should return Maharashtra; got: {names}"
    )


def test_state_detail_by_id(headers):
    resp = requests.get(f"{BASE_URL}/states", headers=headers, params={"country_id": 101}, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No states in DB to fetch by ID")
    sid = items[0].get("id")
    resp2 = requests.get(f"{BASE_URL}/states/{sid}", headers=headers, timeout=10)
    assert resp2.status_code == 200, resp2.text
    detail = resp2.json()
    detail = detail.get("data", detail)
    assert detail.get("state_name") or detail.get("name"), f"Missing state_name in: {detail}"


@skip_if_readonly()
def test_create_state(headers):
    global _created_id
    payload = {
        "state_name": unique("TestState"),
        "country_id": 101,
        "state_code": unique("TS")[:4].upper(),
    }
    resp = requests.post(f"{BASE_URL}/states", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    state = body.get("data", body)
    _created_id = state.get("id")
    assert _created_id, f"No id in response: {body}"
    assert state.get("state_name") or state.get("name"), f"No state_name in response: {body}"
    cid = state.get("country_id")
    assert cid == 101, f"country_id mismatch: {state}"


@skip_if_readonly()
def test_create_state_missing_country_id(headers):
    payload = {"state_name": unique("BadState")}
    resp = requests.post(f"{BASE_URL}/states", headers=headers, json=payload, timeout=10)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


@skip_if_readonly()
def test_create_state_invalid_country_id(headers):
    payload = {
        "state_name": unique("GhostState"),
        "country_id": 999999,
        "state_code": "GH",
    }
    resp = requests.post(f"{BASE_URL}/states", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (404, 422, 400), (
        f"Expected 404/422/400 for non-existent country, got {resp.status_code}: {resp.text}"
    )


@skip_if_readonly()
def test_update_state(headers):
    if not _created_id:
        pytest.skip("No state created to update")
    payload = {"state_name": unique("UpdatedState"), "country_id": 101}
    resp = requests.put(f"{BASE_URL}/states/{_created_id}", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201, 204), resp.text


@skip_if_readonly()
def test_patch_state_status(headers):
    if not _created_id:
        pytest.skip("No state created to patch status")
    resp = requests.patch(
        f"{BASE_URL}/states/{_created_id}/status",
        headers=headers,
        json={"status": "inactive"},
        timeout=10,
    )
    assert resp.status_code in (200, 201, 204), resp.text
    if resp.status_code == 200 and resp.content:
        body = resp.json()
        state = body.get("data", body)
        status_val = state.get("status") or state.get("is_active")
        # status toggled to inactive — accept either falsy or "inactive"
        if status_val is not None:
            assert status_val in (False, 0, "inactive"), f"Unexpected status: {status_val}"
