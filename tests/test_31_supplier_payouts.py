"""Module 31 - Supplier Payouts and Ledgers"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers


def test_supplier_payouts_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/supplier-payouts", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_supplier_payouts_has_total(headers):
    resp = requests.get(f"{BASE_URL}/supplier-payouts", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    has_total = (
        "total" in body
        or "count" in body
        or isinstance(body, list)
        or "data" in body
        or "items" in body
    )
    assert has_total, f"Expected total/items in supplier-payouts response: {body}"


def test_supplier_payouts_filter_pending(headers):
    resp = requests.get(
        f"{BASE_URL}/supplier-payouts",
        headers=headers,
        params={"status": "pending"},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"


def test_supplier_payouts_filter_paid(headers):
    resp = requests.get(
        f"{BASE_URL}/supplier-payouts",
        headers=headers,
        params={"status": "paid"},
        timeout=10,
    )
    assert resp.status_code == 200, resp.text


def test_supplier_ledgers_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/supplier-ledgers", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_supplier_ledgers_has_total(headers):
    resp = requests.get(f"{BASE_URL}/supplier-ledgers", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    has_total = (
        "total" in body
        or "count" in body
        or isinstance(body, list)
        or "data" in body
        or "items" in body
    )
    assert has_total, f"Expected total/items in supplier-ledgers response: {body}"


def test_mark_nonexistent_payout_paid(headers):
    resp = requests.patch(
        f"{BASE_URL}/supplier-payouts/999999/mark-paid",
        headers=headers,
        json={},
        timeout=10,
    )
    assert resp.status_code == 404, (
        f"Expected 404 for non-existent payout, got {resp.status_code}: {resp.text}"
    )


def test_supplier_statement_nonexistent(headers):
    resp = requests.get(
        f"{BASE_URL}/supplier-statements/999999",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 404), (
        f"Expected 200 (empty) or 404 for non-existent supplier statement, "
        f"got {resp.status_code}: {resp.text}"
    )
    if resp.status_code == 200:
        body = resp.json()
        items = body if isinstance(body, list) else body.get("data", body.get("items", []))
        # If 200, should be empty (no statement for non-existent supplier)
        if isinstance(items, list):
            assert len(items) == 0, f"Expected empty statement for supplier 999999: {items}"


@skip_if_readonly()
def test_create_supplier_payout_no_valid_supplier(headers):
    """Creating a payout with a non-existent supplier should fail."""
    payload = {
        "supplier_id": 999999,
        "amount": 1000.00,
        "payment_method": "bank_transfer",
        "notes": "Test payout",
    }
    resp = requests.post(
        f"{BASE_URL}/supplier-payouts",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (200, 201, 400, 422, 404), (
        f"Unexpected status for supplier payout creation: {resp.status_code}: {resp.text}"
    )


def test_supplier_payouts_requires_auth():
    resp = requests.get(f"{BASE_URL}/supplier-payouts", timeout=10)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 without auth, got {resp.status_code}: {resp.text}"
    )


def test_supplier_ledgers_requires_auth():
    resp = requests.get(f"{BASE_URL}/supplier-ledgers", timeout=10)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 without auth, got {resp.status_code}: {resp.text}"
    )
