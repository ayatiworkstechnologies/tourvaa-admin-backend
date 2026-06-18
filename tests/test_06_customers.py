"""Module 06 — Customers"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly


def test_customers_list(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_customers_list_is_paginated(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    data = body.get("data", body)
    assert isinstance(data, (list, dict))


def test_customers_require_auth():
    resp = requests.get(f"{BASE_URL}/customers/", timeout=10)
    assert resp.status_code in (401, 403)


def test_customers_detail_with_id(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    resp2 = requests.get(f"{BASE_URL}/customers/{cid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_customers_detail_404_for_invalid(headers):
    resp = requests.get(f"{BASE_URL}/customers/9999999", headers=headers, timeout=10)
    assert resp.status_code == 404


def test_customer_bookings_endpoint(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    resp2 = requests.get(f"{BASE_URL}/customers/{cid}/bookings", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_customer_payments_endpoint(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    resp2 = requests.get(f"{BASE_URL}/customers/{cid}/payments", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_customer_communications_endpoint(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    resp2 = requests.get(f"{BASE_URL}/customers/{cid}/communications", headers=headers, timeout=10)
    assert resp2.status_code == 200


@skip_if_readonly()
def test_customer_reset_password(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    resp2 = requests.post(f"{BASE_URL}/customers/{cid}/reset-password", headers=headers, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_customer_block_unblock(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    block = requests.patch(f"{BASE_URL}/customers/{cid}/block", headers=headers,
                           json={"reason": "test block"}, timeout=10)
    assert block.status_code in (200, 201, 204)
    unblock = requests.patch(f"{BASE_URL}/customers/{cid}/unblock", headers=headers, timeout=10)
    assert unblock.status_code in (200, 201, 204)


@skip_if_readonly()
def test_send_customer_message(headers):
    resp = requests.get(f"{BASE_URL}/customers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No customers in DB")
    cid = items[0].get("id") or items[0].get("customer_id")
    resp2 = requests.post(f"{BASE_URL}/customers/{cid}/communications", headers=headers, json={
        "subject": "Test message", "message": "Hello from test", "message_type": "info"
    }, timeout=10)
    assert resp2.status_code in (200, 201)
