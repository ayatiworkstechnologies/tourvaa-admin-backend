"""Module 07 - Suppliers"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique


def test_suppliers_list(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_suppliers_require_auth():
    resp = requests.get(f"{BASE_URL}/suppliers/", timeout=10)
    assert resp.status_code in (401, 403)


def test_supplier_detail(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No suppliers in DB")
    sid = items[0].get("id")
    resp2 = requests.get(f"{BASE_URL}/suppliers/{sid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_supplier_detail_404(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/9999999", headers=headers, timeout=10)
    assert resp.status_code == 404


@skip_if_readonly()
def test_create_supplier(headers, first_country_id):
    payload = {
        "user_id": 1,
        "supplier_name": unique("SupplierTest"),
        "supplier_type": "hotel",
        "country_id": first_country_id,
    }
    resp = requests.post(f"{BASE_URL}/suppliers/", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)
    body = resp.json()
    sid = (body.get("data") or body).get("id")
    assert sid


@skip_if_readonly()
def test_approve_supplier(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    pending = [s for s in items if s.get("approval_status") in ("pending", None)]
    if not pending:
        pytest.skip("No pending supplier to approve")
    sid = pending[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/suppliers/{sid}/approve", headers=headers,
                           json={"admin_comments": "Test approve"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_reject_supplier(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    pending = [s for s in items if s.get("approval_status") in ("pending", None)]
    if not pending:
        pytest.skip("No pending supplier to reject")
    sid = pending[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/suppliers/{sid}/reject", headers=headers,
                           json={"rejection_reason": "Test rejection"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_supplier_markup_update(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No suppliers in DB")
    sid = items[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/suppliers/{sid}/markup", headers=headers,
                           json={"markup_type": "percentage", "markup_value": 10.0}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_supplier_markup_invalid_type(headers):
    resp = requests.get(f"{BASE_URL}/suppliers/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No suppliers in DB")
    sid = items[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/suppliers/{sid}/markup", headers=headers,
                           json={"markup_type": "invalid_type", "markup_value": 10.0}, timeout=10)
    assert resp2.status_code in (400, 422)
