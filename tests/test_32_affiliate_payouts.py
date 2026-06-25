"""Module 32 — Affiliate Payouts, Conversions, Commissions"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

_first_affiliate_id = None


def _get_first_affiliate_id(headers) -> int | None:
    """Helper to fetch the first affiliate id from the affiliates list."""
    resp = requests.get(f"{BASE_URL}/affiliates", headers=headers, timeout=10)
    if resp.status_code != 200:
        return None
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if items:
        return items[0].get("id") or items[0].get("affiliate_id")
    return None


def test_affiliate_payouts_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/affiliate-payouts", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_affiliate_payouts_is_list(headers):
    resp = requests.get(f"{BASE_URL}/affiliate-payouts", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"


def test_affiliate_payouts_filter_pending(headers):
    resp = requests.get(
        f"{BASE_URL}/affiliate-payouts",
        headers=headers,
        params={"status": "pending"},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), resp.text


def test_affiliates_list_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/affiliates", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_affiliates_list_is_list(headers):
    resp = requests.get(f"{BASE_URL}/affiliates", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"


def test_affiliate_conversions(headers):
    affiliate_id = _get_first_affiliate_id(headers)
    if not affiliate_id:
        pytest.skip("No affiliates in DB to test conversions")
    resp = requests.get(
        f"{BASE_URL}/affiliates/{affiliate_id}/conversions",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of conversions, got: {type(items)}"


def test_affiliate_commissions(headers):
    affiliate_id = _get_first_affiliate_id(headers)
    if not affiliate_id:
        pytest.skip("No affiliates in DB to test commissions")
    resp = requests.get(
        f"{BASE_URL}/affiliates/{affiliate_id}/commissions",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Commissions endpoint returns a summary dict with an 'entries' list
    data = body.get("data", body)
    assert isinstance(data, (dict, list)), f"Expected dict or list of commissions, got: {type(data)}"
    if isinstance(data, dict):
        assert "entries" in data or "total_conversions" in data, f"Unexpected commission shape: {data.keys()}"


def test_affiliate_links(headers):
    affiliate_id = _get_first_affiliate_id(headers)
    if not affiliate_id:
        pytest.skip("No affiliates in DB to test links")
    resp = requests.get(
        f"{BASE_URL}/affiliates/{affiliate_id}/links",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of links, got: {type(items)}"


def test_affiliate_clicks(headers):
    affiliate_id = _get_first_affiliate_id(headers)
    if not affiliate_id:
        pytest.skip("No affiliates in DB to test clicks")
    resp = requests.get(
        f"{BASE_URL}/affiliates/{affiliate_id}/clicks",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of clicks, got: {type(items)}"


@skip_if_readonly()
def test_create_affiliate_payout_invalid_affiliate(headers):
    """Creating a payout with a non-existent affiliate should return 400/422/404."""
    payload = {
        "affiliate_id": 999999,
        "amount": 500.00,
        "payment_method": "bank_transfer",
    }
    resp = requests.post(
        f"{BASE_URL}/affiliate-payouts",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (400, 422, 404), (
        f"Expected 400/422/404 for invalid affiliate payout, "
        f"got {resp.status_code}: {resp.text}"
    )


def test_affiliate_payouts_requires_auth():
    resp = requests.get(f"{BASE_URL}/affiliate-payouts", timeout=10)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 without auth, got {resp.status_code}: {resp.text}"
    )
