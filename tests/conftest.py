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


def unique_phone(country_code: str = "+91") -> str:
    """A syntactically valid, collision-free phone number for test fixtures."""
    digits = str(uuid.uuid4().int)[:9]
    return f"{country_code}{digits}"


def get_admin_token() -> str:
    resp = login_with_retry(ADMIN_EMAIL, ADMIN_PASSWORD, attempts=12, backoff=6.0)
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


def create_active_account(role_slug: str, user_type: str, name: str, email: str, phone: str, password: str):
    """Create an already-ACTIVE user (+ profile row) directly in the DB.

    Real self-registration (`register_unified_user`) requires clicking a
    one-way-hashed email verification link before a password can even be set -
    the raw token only ever exists in the outgoing email, so a black-box HTTP
    test can't drive that flow end-to-end. This bypasses registration entirely
    for FIXTURE SETUP only; the actual behavior under test (login, portal
    endpoints, approval endpoints, etc.) still goes through real HTTP against
    BASE_URL exactly as before.
    """
    import app.main  # noqa: F401 - ensures every model is registered before mapper configuration
    from app.utils.money import utcnow
    from app.database import SessionLocal
    from app.models.users import User, UserRole
    from app.models.roles import Role
    from app.models.customers import Customer
    from app.models.suppliers import Supplier
    from app.models.agents import Agent
    from app.models.affiliates import Affiliate
    from app.auth.security import hash_password

    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.slug == role_slug, Role.is_active == True).first()
        assert role, f"Role {role_slug!r} is not seeded"
        user = User(
            name=name, email=email, phone=phone, country_code="+91", mobile_number=phone,
            # hash_password() (not hash_password_plain()) matches every other
            # test in this suite, which POSTs the raw password directly to
            # /auth/login - same convention as the seeded super-admin account.
            password=hash_password(password), role_id=role.id, user_type=user_type,
            is_active=True, approval_status="NOT_REQUIRED",
            email_verified=True, email_verified_at=utcnow(), account_status="ACTIVE",
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        if role_slug == "customer":
            db.add(Customer(user_id=user.id, first_name=name, last_name="", full_name=name, email=email, phone=phone, status="active", email_verified=True))
        elif role_slug == "supplier":
            # Left un-approved on purpose - test_36 exercises the real
            # POST /suppliers/{id}/approve endpoint against this fixture.
            db.add(Supplier(user_id=user.id, supplier_name=name, status="inactive", approval_status="PENDING"))
        elif role_slug == "agent-reseller":
            db.add(Agent(user_id=user.id, agent_name=name, status="active", approval_status="NOT_REQUIRED"))
        elif role_slug == "affiliate":
            # Left un-approved on purpose, mirroring the supplier fixture -
            # tests that need an approved+active affiliate call the real
            # POST /affiliates/{id}/approve endpoint themselves.
            db.add(Affiliate(user_id=user.id, name=name, email=email, phone=phone, status="inactive", approval_status="pending", commission_percentage=10))
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


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
