"""Module 08 — Agents"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly, unique


def test_agents_list(headers):
    resp = requests.get(f"{BASE_URL}/agents/", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_agents_require_auth():
    resp = requests.get(f"{BASE_URL}/agents/", timeout=10)
    assert resp.status_code in (401, 403)


def test_agent_detail(headers):
    resp = requests.get(f"{BASE_URL}/agents/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No agents in DB")
    aid = items[0].get("id")
    resp2 = requests.get(f"{BASE_URL}/agents/{aid}", headers=headers, timeout=10)
    assert resp2.status_code == 200


def test_agent_detail_404(headers):
    resp = requests.get(f"{BASE_URL}/agents/9999999", headers=headers, timeout=10)
    assert resp.status_code == 404


@skip_if_readonly()
def test_create_agent(headers, first_country_id):
    payload = {
        "user_id": 1,
        "agent_name": unique("AgentTest"),
        "agent_type": "travel_agency",
        "country_id": first_country_id,
    }
    resp = requests.post(f"{BASE_URL}/agents/", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201)


@skip_if_readonly()
def test_approve_agent(headers):
    resp = requests.get(f"{BASE_URL}/agents/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    pending = [a for a in items if a.get("approval_status") in ("pending", None)]
    if not pending:
        pytest.skip("No pending agent to approve")
    aid = pending[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/agents/{aid}/approve", headers=headers,
                           json={"admin_comments": "Test approve"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_reject_agent(headers):
    resp = requests.get(f"{BASE_URL}/agents/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    pending = [a for a in items if a.get("approval_status") in ("pending", None)]
    if not pending:
        pytest.skip("No pending agent to reject")
    aid = pending[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/agents/{aid}/reject", headers=headers,
                           json={"rejection_reason": "Test rejection"}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_agent_discount_update(headers):
    resp = requests.get(f"{BASE_URL}/agents/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No agents in DB")
    aid = items[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/agents/{aid}/discount", headers=headers,
                           json={"discount_type": "percentage", "discount_value": 5.0}, timeout=10)
    assert resp2.status_code in (200, 201, 204)


@skip_if_readonly()
def test_agent_discount_invalid_type(headers):
    resp = requests.get(f"{BASE_URL}/agents/", headers=headers, timeout=10)
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    if not items:
        pytest.skip("No agents in DB")
    aid = items[0]["id"]
    resp2 = requests.patch(f"{BASE_URL}/agents/{aid}/discount", headers=headers,
                           json={"discount_type": "invalid_type", "discount_value": 5.0}, timeout=10)
    assert resp2.status_code in (400, 422)
