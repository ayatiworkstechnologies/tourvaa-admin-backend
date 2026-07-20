"""
Shared test configuration and fixtures for Tourvaa backend module tests.
All tests hit the live server at http://127.0.0.1:8000/api
Write/destructive tests require TOURVAA_WRITE_TESTS=1
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = "http://127.0.0.1:8000/api"
ADMIN_EMAIL = "admin@tourvaa.com"
ADMIN_PASSWORD = "Admin@123"

WRITE_TESTS = os.environ.get("TOURVAA_WRITE_TESTS", "0") == "1"


def skip_if_readonly(reason="write test - set TOURVAA_WRITE_TESTS=1 to run"):
    return pytest.mark.skipif(not WRITE_TESTS, reason=reason)


def unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def get_admin_token() -> str:
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    }, timeout=10)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("data", {}).get("access_token") or data.get("access_token")
    assert token, f"No token in response: {data}"
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login_with_retry(email: str, password: str, attempts: int = 6, backoff: float = 6.0):
    """POST /auth/login, retrying past transient 429s.

    /auth/login is IP-rate-limited (10 calls/60s). Full-suite runs make far more
    than 10 login calls well within a minute, so any fixture that logs in as a
    freshly-registered role user can get legitimately rate-limited even though
    the login itself would otherwise succeed. This is not a bug to test around
    with a looser assertion (that would mask a real 401/403) - it's a timing
    issue, so retry with backoff instead.
    """
    last = None
    for _ in range(attempts):
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
        if resp.status_code != 429:
            return resp
        last = resp
        time.sleep(backoff)
    return last


@pytest.fixture(scope="session")
def token():
    return get_admin_token()


@pytest.fixture(scope="session")
def headers(token):
    return auth_headers(token)


@pytest.fixture(scope="session")
def first_tour_id(headers):
    resp = requests.get(f"{BASE_URL}/tours", headers=headers, timeout=10)
    if resp.status_code == 200:
        body = resp.json()
        items = body if isinstance(body, list) else body.get("data", body.get("items", []))
        if items:
            return items[0].get("id") or items[0].get("tour_id")
    return 1


@pytest.fixture(scope="session")
def first_country_id(headers):
    resp = requests.get(f"{BASE_URL}/countries", headers=headers, timeout=10)
    if resp.status_code == 200:
        items = resp.json()
        items = items if isinstance(items, list) else items.get("data", [])
        if items:
            return items[0]["id"]
    return 1


@pytest.fixture(scope="session")
def first_booking_id(headers):
    resp = requests.get(f"{BASE_URL}/bookings", headers=headers, timeout=10)
    if resp.status_code == 200:
        items = resp.json().get("items", [])
        if items:
            return items[0]["id"]
    return None


@pytest.fixture(scope="session")
def first_category_id(headers):
    resp = requests.get(f"{BASE_URL}/tour-categories", headers=headers, timeout=10)
    if resp.status_code == 200:
        items = resp.json()
        items = items if isinstance(items, list) else items.get("data", [])
        if items:
            return items[0]["id"]
    return 1
