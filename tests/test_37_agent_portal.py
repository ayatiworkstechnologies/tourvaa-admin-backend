"""Module 37 - Agent Self-Service Portal (/api/agents/me, /api/agent/*)

Note: unlike customers/suppliers, agents have no dedicated /api/agent/bookings,
/customers, /invoices, or /tours endpoints - the frontend's agent portal pages
reuse the shared admin endpoints (e.g. /api/bookings), which apply row-level
scoping server-side based on the caller's role (see get_bookings() in
app/services/bookings.py: role == "agent" filters to Booking.agent.user_id).
Whether that succeeds depends on the agent-reseller role having the relevant
view permission seeded - both outcomes (200 scoped, or 403 no permission) are
treated as valid here; only 5xx is a real failure.
"""
import pytest
import requests

from tests.conftest import BASE_URL, unique, skip_if_readonly, login_with_retry


def _register_agent():
    name = f"Portal Test Agent {unique('n')}"
    email = f"{unique('agt')}@example.com"
    password = "Agent@1234"
    resp = requests.post(f"{BASE_URL}/auth/register/agent", json={
        "name": name, "email": email, "phone": "+919876522222", "password": password,
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    return name, email, password


def _find_agent_id_by_name(admin_headers, name):
    resp = requests.get(f"{BASE_URL}/agents", params={"search": name, "limit": 10}, headers=admin_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    items = resp.json().get("items", [])
    match = next((a for a in items if a.get("name") == name or a.get("agent_name") == name), None)
    return match["id"] if match else None


@pytest.fixture(scope="module")
def agent_ctx(headers):
    name, email, password = _register_agent()

    agent_id = _find_agent_id_by_name(headers, name)
    assert agent_id, f"Newly registered agent {name!r} not found via admin search"

    approve = requests.post(f"{BASE_URL}/agents/{agent_id}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text

    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email, "agent_id": agent_id}


@pytest.fixture()
def agent_headers(agent_ctx):
    return agent_ctx["headers"]


# ---------------------------------------------------------------------------
# Registration / approval gate (mirrors supplier flow)
# ---------------------------------------------------------------------------

def test_agent_login_blocked_until_approved():
    _, email, password = _register_agent()
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
    # 429 is also acceptable: /auth/login is IP-rate-limited (10 calls/60s) and the
    # full suite makes far more than 10 login calls, so this can legitimately trip
    # under heavy test-suite load rather than the approval-status gate itself.
    assert resp.status_code in (403, 429), resp.text


def test_agent_can_login_after_approval(agent_ctx):
    assert agent_ctx["headers"]["Authorization"].startswith("Bearer ")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def test_agent_me_get(agent_headers):
    resp = requests.get(f"{BASE_URL}/agents/me", headers=agent_headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_agent_me_update(agent_headers):
    resp = requests.put(f"{BASE_URL}/agents/me", json={
        "years_in_operation": 3,
    }, headers=agent_headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_agent_me_requires_auth():
    resp = requests.get(f"{BASE_URL}/agents/me", timeout=10)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Shared endpoints reused by the agent portal (see module docstring)
# ---------------------------------------------------------------------------

def test_agent_scoped_bookings_access(agent_headers):
    resp = requests.get(f"{BASE_URL}/bookings", headers=agent_headers, timeout=10)
    assert resp.status_code in (200, 403), resp.text
    if resp.status_code == 200:
        assert "items" in resp.json()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def test_agent_messages_list(agent_headers):
    resp = requests.get(f"{BASE_URL}/agent/messages", headers=agent_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


@skip_if_readonly()
def test_agent_send_message(agent_headers):
    resp = requests.post(f"{BASE_URL}/agent/messages", json={
        "subject": "Commission question", "message": "When does my commission get paid out?",
    }, headers=agent_headers, timeout=10)
    assert resp.status_code in (200, 201), resp.text
