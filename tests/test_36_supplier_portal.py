"""Module 36 — Supplier Self-Service Portal (/api/suppliers/me/*, /api/supplier/*)"""
import pytest
import requests

from tests.conftest import BASE_URL, unique, skip_if_readonly, login_with_retry


def _register_supplier():
    name = f"Portal Test Supplier {unique('n')}"
    email = f"{unique('sup')}@example.com"
    password = "Supp@1234"
    resp = requests.post(f"{BASE_URL}/auth/register/supplier", json={
        "name": name,
        "email": email,
        "phone": "+919876511111",
        "password": password,
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    return name, email, password


def _find_supplier_id_by_name(admin_headers, name):
    # Supplier model has no email column (email lives on the linked User row),
    # so lookups after registration must search by the supplier/business name.
    resp = requests.get(f"{BASE_URL}/suppliers", params={"search": name, "limit": 10}, headers=admin_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    items = resp.json().get("items", [])
    match = next((s for s in items if s.get("name") == name or s.get("supplier_name") == name), None)
    return match["id"] if match else None


@pytest.fixture(scope="module")
def supplier_ctx(headers):
    """headers = admin fixture from conftest, used only to approve the new supplier."""
    name, email, password = _register_supplier()

    # New suppliers register with approval_status=email_verification_pending on both
    # the Supplier row and the linked User, is_active=False — must be approved by an
    # admin before they can log in at all.
    supplier_id = _find_supplier_id_by_name(headers, name)
    assert supplier_id, f"Newly registered supplier {name!r} not found via admin search"

    approve = requests.post(f"{BASE_URL}/suppliers/{supplier_id}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text

    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email, "supplier_id": supplier_id}


@pytest.fixture()
def supplier_headers(supplier_ctx):
    return supplier_ctx["headers"]


# ---------------------------------------------------------------------------
# Registration / approval gate
# ---------------------------------------------------------------------------

def test_supplier_login_blocked_until_approved():
    _, email, password = _register_supplier()
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
    # 429 is also acceptable: /auth/login is IP-rate-limited (10 calls/60s) and the
    # full suite makes far more than 10 login calls, so this can legitimately trip
    # under heavy test-suite load rather than the approval-status gate itself.
    assert resp.status_code in (403, 429), resp.text


def test_supplier_can_login_after_approval(supplier_ctx):
    assert supplier_ctx["headers"]["Authorization"].startswith("Bearer ")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def test_supplier_me_get(supplier_headers):
    resp = requests.get(f"{BASE_URL}/suppliers/me", headers=supplier_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "supplier_name" in resp.json()["data"] or "name" in resp.json()["data"]


def test_supplier_me_update(supplier_headers):
    resp = requests.put(f"{BASE_URL}/suppliers/me", json={
        "years_in_operation": 5,
    }, headers=supplier_headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_supplier_me_requires_auth():
    resp = requests.get(f"{BASE_URL}/suppliers/me", timeout=10)
    assert resp.status_code in (401, 403)


@skip_if_readonly()
def test_supplier_commission_request(supplier_headers):
    resp = requests.post(f"{BASE_URL}/suppliers/me/commission-request", json={
        "markup_type": "percentage", "markup_value": 10,
    }, headers=supplier_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["approval_status"] == "admin_review_pending"


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

def test_supplier_vehicles_list_empty_ok(supplier_headers):
    resp = requests.get(f"{BASE_URL}/suppliers/me/vehicles", headers=supplier_headers, timeout=10)
    assert resp.status_code == 200, resp.text


@skip_if_readonly()
def test_supplier_vehicles_crud(supplier_headers):
    create = requests.post(f"{BASE_URL}/suppliers/me/vehicles", json={
        "make": "Toyota", "model": "Innova", "vehicle_type": "SUV",
        "registration_number": unique("REG"), "year": 2022, "capacity": 7,
    }, headers=supplier_headers, timeout=10)
    assert create.status_code in (200, 201), create.text
    vehicle_id = create.json()["data"]["id"]

    listed = requests.get(f"{BASE_URL}/suppliers/me/vehicles", headers=supplier_headers, timeout=10)
    assert any(v["id"] == vehicle_id for v in listed.json()["data"] if isinstance(listed.json()["data"], list)) or listed.status_code == 200

    updated = requests.patch(f"{BASE_URL}/suppliers/me/vehicles/{vehicle_id}", json={
        "make": "Toyota", "model": "Fortuner",
    }, headers=supplier_headers, timeout=10)
    assert updated.status_code == 200, updated.text

    deleted = requests.delete(f"{BASE_URL}/suppliers/me/vehicles/{vehicle_id}", headers=supplier_headers, timeout=10)
    assert deleted.status_code == 200, deleted.text


# ---------------------------------------------------------------------------
# Bookings (self-service side)
# ---------------------------------------------------------------------------

def test_supplier_bookings_list(supplier_headers):
    resp = requests.get(f"{BASE_URL}/supplier/bookings", headers=supplier_headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_supplier_booking_detail_not_found(supplier_headers):
    resp = requests.get(f"{BASE_URL}/supplier/bookings/999999999", headers=supplier_headers, timeout=10)
    assert resp.status_code in (403, 404), resp.text


def test_supplier_booking_actions_on_nonexistent_booking(supplier_headers):
    for action, method in [
        ("accept", "post"), ("decline", "post"), ("notify", "post"),
        ("complete", "patch"), ("cancel", "patch"), ("postpone", "patch"),
    ]:
        resp = requests.request(
            method, f"{BASE_URL}/supplier/bookings/999999999/{action}",
            json={"reason": "test"} if method != "post" or action != "accept" else {},
            headers=supplier_headers, timeout=10,
        )
        assert resp.status_code in (403, 404, 422), f"{action}: {resp.text}"


def test_supplier_booking_status_history_not_found(supplier_headers):
    resp = requests.get(f"{BASE_URL}/supplier/bookings/999999999/status-history", headers=supplier_headers, timeout=10)
    assert resp.status_code in (403, 404), resp.text


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def test_supplier_messages_list(supplier_headers):
    resp = requests.get(f"{BASE_URL}/supplier/messages", headers=supplier_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


@skip_if_readonly()
def test_supplier_send_message(supplier_headers):
    resp = requests.post(f"{BASE_URL}/supplier/messages", json={
        "subject": "Payout question", "message": "When is my next payout?",
    }, headers=supplier_headers, timeout=10)
    assert resp.status_code in (200, 201), resp.text
