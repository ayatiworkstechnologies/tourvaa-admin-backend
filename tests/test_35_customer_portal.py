"""Module 35 - Customer Self-Service Portal (/api/customer/*)"""
import pytest
import requests

from tests.conftest import BASE_URL, unique, skip_if_readonly


def _register_and_login_customer():
    email = f"{unique('cust')}@example.com"
    password = "Cust@1234"
    resp = requests.post(f"{BASE_URL}/auth/register/customer", json={
        "name": "Portal Test Customer",
        "email": email,
        "phone": "+919876500000",
        "password": password,
    }, timeout=10)
    assert resp.status_code in (200, 201), resp.text

    login = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email, "password": password,
    }, timeout=10)
    assert login.status_code == 200, login.text
    token = login.json().get("data", {}).get("access_token")
    assert token, login.text
    return {"Authorization": f"Bearer {token}"}, email, password


@pytest.fixture(scope="module")
def customer_ctx():
    headers, email, password = _register_and_login_customer()
    return {"headers": headers, "email": email, "password": password}


@pytest.fixture()
def customer_headers(customer_ctx):
    # Re-read on every call (not module-scoped) so it reflects the latest
    # token after test_customer_change_password_success rotates it.
    return customer_ctx["headers"]


# ---------------------------------------------------------------------------
# Registration / login
# ---------------------------------------------------------------------------

def test_customer_registration_creates_immediately_usable_account(customer_ctx):
    # Confirms REQUIRE_EMAIL_VERIFICATION=false + auto-approval for the customer role.
    assert customer_ctx["headers"]["Authorization"].startswith("Bearer ")


def test_customer_duplicate_email_registration_rejected(customer_ctx):
    resp = requests.post(f"{BASE_URL}/auth/register/customer", json={
        "name": "Dup", "email": customer_ctx["email"], "password": "Cust@1234",
    }, timeout=10)
    assert resp.status_code in (400, 409, 422), resp.text


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def test_customer_profile_get(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/profile", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "email" in data


def test_customer_profile_update(customer_headers):
    resp = requests.put(f"{BASE_URL}/customer/profile", json={
        "first_name": "Portal", "last_name": "Tester",
    }, headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["first_name"] == "Portal"


def test_customer_profile_requires_auth():
    resp = requests.get(f"{BASE_URL}/customer/profile", timeout=10)
    assert resp.status_code in (401, 403)


@skip_if_readonly()
def test_customer_change_password_wrong_current_rejected(customer_headers):
    resp = requests.post(f"{BASE_URL}/customer/change-password", json={
        "current_password": "WrongCurrent@1", "new_password": "NewPass@1234",
    }, headers=customer_headers, timeout=10)
    assert resp.status_code == 400, resp.text


@skip_if_readonly()
def test_customer_change_password_success(customer_ctx):
    headers = customer_ctx["headers"]
    new_password = "NewPass@1234"
    resp = requests.post(f"{BASE_URL}/customer/change-password", json={
        "current_password": customer_ctx["password"], "new_password": new_password,
    }, headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text

    # Old token is invalidated (token_version bumped) - old password no longer works.
    relogin_old = requests.post(f"{BASE_URL}/auth/login", json={
        "email": customer_ctx["email"], "password": customer_ctx["password"],
    }, timeout=10)
    assert relogin_old.status_code == 401

    relogin_new = requests.post(f"{BASE_URL}/auth/login", json={
        "email": customer_ctx["email"], "password": new_password,
    }, timeout=10)
    assert relogin_new.status_code == 200
    customer_ctx["password"] = new_password
    customer_ctx["headers"] = {
        "Authorization": f"Bearer {relogin_new.json()['data']['access_token']}"
    }


# ---------------------------------------------------------------------------
# Saved travellers
# ---------------------------------------------------------------------------

def test_customer_travellers_list_empty_ok(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/travellers", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


@skip_if_readonly()
def test_customer_travellers_crud(customer_headers):
    create = requests.post(f"{BASE_URL}/customer/travellers", json={
        "traveller_name": "Jane Traveller", "traveller_type": "adult", "age": 30,
    }, headers=customer_headers, timeout=10)
    assert create.status_code in (200, 201), create.text
    traveller_id = create.json()["data"]["id"]

    listed = requests.get(f"{BASE_URL}/customer/travellers", headers=customer_headers, timeout=10)
    assert any(t["id"] == traveller_id for t in listed.json()["items"])

    updated = requests.put(f"{BASE_URL}/customer/travellers/{traveller_id}", json={
        "traveller_name": "Jane Updated", "traveller_type": "adult",
    }, headers=customer_headers, timeout=10)
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["traveller_name"] == "Jane Updated"

    deleted = requests.delete(f"{BASE_URL}/customer/travellers/{traveller_id}", headers=customer_headers, timeout=10)
    assert deleted.status_code == 200, deleted.text


# ---------------------------------------------------------------------------
# User-scoped wishlist
# ---------------------------------------------------------------------------

def test_customer_wishlist_list(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/wishlist", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


@skip_if_readonly()
def test_customer_wishlist_crud_is_bound_to_user(customer_headers):
    tours = requests.get(f"{BASE_URL}/public/tours?limit=1", timeout=10)
    assert tours.status_code == 200, tours.text
    items = tours.json().get("items", [])
    if not items:
        pytest.skip("No published tour available to save")
    tour_id = items[0]["id"]

    profile = requests.get(f"{BASE_URL}/customer/profile", headers=customer_headers, timeout=10)
    user_id = profile.json()["data"]["user_id"]

    created = requests.post(f"{BASE_URL}/customer/wishlist/{tour_id}", headers=customer_headers, timeout=10)
    assert created.status_code in (200, 201), created.text
    assert created.json()["data"]["user_id"] == user_id

    duplicate = requests.post(f"{BASE_URL}/customer/wishlist/{tour_id}", headers=customer_headers, timeout=10)
    assert duplicate.status_code == 200, duplicate.text

    listed = requests.get(f"{BASE_URL}/customer/wishlist", headers=customer_headers, timeout=10)
    matches = [item for item in listed.json()["items"] if item["id"] == tour_id]
    assert len(matches) == 1
    assert matches[0]["user_id"] == user_id

    deleted = requests.delete(f"{BASE_URL}/customer/wishlist/{tour_id}", headers=customer_headers, timeout=10)
    assert deleted.status_code == 200, deleted.text


# ---------------------------------------------------------------------------
# Bookings / payments / invoices / cancellations (read + price calc)
# ---------------------------------------------------------------------------

def test_customer_bookings_list(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/bookings", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


def test_customer_calculate_price(customer_headers, first_tour_id):
    if not first_tour_id:
        pytest.skip("No tour available to price")
    resp = requests.post(f"{BASE_URL}/customer/bookings/calculate-price", json={
        "tour_id": first_tour_id, "adults_count": 2, "children_count": 0,
        "tour_name": "Price Check", "tour_date": "2026-09-01",
    }, headers=customer_headers, timeout=10)
    assert resp.status_code in (200, 400, 404, 422), resp.text


def test_customer_payments_list(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/payments", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_customer_invoices_list(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/invoices", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_customer_cancellations_list(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/cancellations", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


def test_customer_booking_detail_not_found(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/bookings/999999999", headers=customer_headers, timeout=10)
    assert resp.status_code == 404, resp.text


def test_customer_cancel_nonexistent_booking(customer_headers):
    resp = requests.post(f"{BASE_URL}/customer/bookings/999999999/cancel", json={
        "reason": "Change of plans",
    }, headers=customer_headers, timeout=10)
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def test_customer_messages_list(customer_headers):
    resp = requests.get(f"{BASE_URL}/customer/messages", headers=customer_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


@skip_if_readonly()
def test_customer_send_message(customer_headers):
    resp = requests.post(f"{BASE_URL}/customer/messages", json={
        "subject": "Question about my trip", "message": "Can I add an extra traveller?",
    }, headers=customer_headers, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["data"]["subject"] == "Question about my trip"
