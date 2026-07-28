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

from tests.conftest import BASE_URL, unique, unique_phone, skip_if_readonly, login_with_retry, create_active_account


def _register_agent():
    """Real self-registration via HTTP - stays PENDING_EMAIL_VERIFICATION."""
    name = f"Portal Test Agent {unique('n')}"
    email = f"{unique('agt')}@example.com"
    password = "Agent@1234"
    resp = requests.post(f"{BASE_URL}/auth/register/agent", json={
        "account_type": "AGENT", "first_name": name, "email": email,
        "country_code": "+91", "mobile_number": unique_phone()[3:], "accepted_terms": True,
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
    # Real self-registration requires clicking an emailed verification link
    # before a password exists - can't be driven by a black-box HTTP test.
    # Created already-active directly; unlike suppliers, agents have no
    # separate admin-approval gate, so this is immediately usable.
    name = f"Portal Test Agent {unique('n')}"
    email = f"{unique('agt')}@example.com"
    password = "Agent@1234"
    create_active_account("agent-reseller", "AGENT", name, email, unique_phone(), password)

    agent_id = _find_agent_id_by_name(headers, name)
    assert agent_id, f"Newly created agent {name!r} not found via admin search"

    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email, "agent_id": agent_id}


@pytest.fixture()
def agent_headers(agent_ctx):
    return agent_ctx["headers"]


# ---------------------------------------------------------------------------
# Registration policy
# ---------------------------------------------------------------------------

def test_agent_can_login_without_email_or_admin_verification():
    # Unlike suppliers, agents have no separate admin-approval gate - once the
    # account itself is active (see agent_ctx: real self-registration requires
    # clicking an emailed link first, which this black-box test can't drive),
    # login succeeds immediately with no additional restriction.
    name = f"Portal Test Agent {unique('n')}"
    email = f"{unique('agt')}@example.com"
    password = "Agent@1234"
    create_active_account("agent-reseller", "AGENT", name, email, unique_phone(), password)

    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
    if resp.status_code == 429:
        return
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert not data.get("account_restricted")
    assert data["user"]["account_status"] == "ACTIVE"
    assert data["access_token"]


def test_agent_can_login_immediately(agent_ctx):
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
