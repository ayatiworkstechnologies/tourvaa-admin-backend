"""Module 09 — Affiliates"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique


def test_affiliates_list(headers):
    resp = requests.get(f"{BASE_URL}/affiliates/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_affiliates_require_auth():
    resp = requests.get(f"{BASE_URL}/affiliates/", timeout=10)
    assert resp.status_code in (401, 403)


def test_affiliate_detail(headers):
    resp = requests.get(f"{BASE_URL}/affiliates/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No affiliates in DB")
    afid = items[0].get("id")
    resp2 = requests.get(f"{BASE_URL}/affiliates/{afid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_affiliate_detail_404(headers):
    resp = requests.get(f"{BASE_URL}/affiliates/9999999", headers=headers, timeout=10)
    assert resp.status_code == 404


@skip_if_readonly()
def test_create_affiliate(headers, first_country_id):
    payload = {
        "name": unique("AffiliateTest"),
        "email": f"{unique('aff')}@test.com",
        "phone": "9876543210",
        "business_type": "individual",
        "country_id": first_country_id,
    }
    resp = requests.post(f"{BASE_URL}/affiliates/", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)


@skip_if_readonly()
def test_approve_affiliate(headers):
    resp = requests.get(f"{BASE_URL}/affiliates/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    pending = [a for a in items if a.get("approval_status") in ("pending", None)]
    if not pending:
        pytest.skip("No pending affiliate to approve")
    afid = pending[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/affiliates/{afid}/approve", headers=headers,
                           json={"admin_comments": "Approved"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_reject_affiliate(headers):
    resp = requests.get(f"{BASE_URL}/affiliates/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    pending = [a for a in items if a.get("approval_status") in ("pending", None)]
    if not pending:
        pytest.skip("No pending affiliate to reject")
    afid = pending[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/affiliates/{afid}/reject", headers=headers,
                           json={"rejection_reason": "Test rejection"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_affiliate_api_link_update(headers):
    resp = requests.get(f"{BASE_URL}/affiliates/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No affiliates in DB")
    afid = items[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/affiliates/{afid}/api-link", headers=headers,
                           json={"api_link": "https://partner.example.com/api"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)
