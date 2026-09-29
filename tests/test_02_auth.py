"""Module 02 - Authentication"""
import pytest
import requests
from tests.conftest import (
    BASE_URL,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ensure_negative_login_account,
    login_with_retry,
    skip_if_readonly,
)


def test_login_valid_credentials():
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
    }, timeout=10)
    assert resp.status_code == 200


def test_login_returns_token():
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
    }, timeout=10)
    data = resp.json()
    token = data.get("data", {}).get("access_token") or data.get("access_token")
    assert token and len(token) > 20


def test_login_invalid_password():
    # Targets a disposable account, NOT the shared super-admin: the lockout
    # policy counts failures per user row, and a bad password against the admin
    # locks it out (HTTP 423), taking the entire session-scoped admin fixture
    # chain - and every test depending on it - down with it.
    email = ensure_negative_login_account()
    resp = login_with_retry(email, "WrongPassword")
    # 401 = rejected; 423 = the disposable account itself hit the lockout
    # threshold, which is still a correct rejection of a bad password.
    assert resp.status_code in (400, 401, 422, 423), resp.text


def test_login_repeated_bad_passwords_lock_the_account():
    """A real (existing) user is locked out after LOGIN_MAX_FAILED_ATTEMPTS."""
    from app.config import settings

    email = ensure_negative_login_account()
    seen_locked = False
    # login_with_retry() retries past the shared-IP 429 rate limit and returns
    # the first REAL response, so each iteration below is exactly one attempt
    # that actually reached the password check.
    #
    # login_user() sets the lock ON the LOGIN_MAX_FAILED_ATTEMPTS-th failure but
    # still answers that call 401; the 423 only surfaces on the NEXT attempt.
    # Budget one extra request beyond the threshold.
    for _ in range(settings.LOGIN_MAX_FAILED_ATTEMPTS + 1):
        resp = login_with_retry(email, "WrongPassword")
        assert resp.status_code in (400, 401, 422, 423), resp.text
        if resp.status_code == 423:
            seen_locked = True
            break
    # The account locks within the configured number of real failed attempts.
    assert seen_locked, (
        f"{email} was not locked within {settings.LOGIN_MAX_FAILED_ATTEMPTS} "
        "failed attempts - brute-force protection is not working"
    )
    # And the correct password is refused while the lock is in force.
    locked_resp = login_with_retry(email, "CorrectHorse9!")
    assert locked_resp.status_code == 423, locked_resp.text
    # Leave the shared DB clean for the next run.
    ensure_negative_login_account()


def test_login_invalid_email():
    resp = login_with_retry("notexist@example.com", "any")
    assert resp.status_code in (400, 401, 422), resp.text


def test_auth_me_with_token(headers):
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_auth_me_returns_user_info(headers):
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
    body = resp.json()
    # /auth/me → {"data": {"user": {...}}} or flat shapes
    import json
    assert ADMIN_EMAIL in json.dumps(body), f"Admin email not in /auth/me response: {body}"


def test_auth_me_without_token_fails():
    resp = requests.get(f"{BASE_URL}/auth/me", timeout=10)
    assert resp.status_code in (401, 403)


def test_protected_endpoint_without_token_blocked():
    resp = requests.get(f"{BASE_URL}/users/", timeout=10)
    assert resp.status_code in (401, 403)


def test_login_history_endpoint(headers):
    resp = requests.get(f"{BASE_URL}/auth/login-history", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_forgot_password_returns_safe_response():
    resp = requests.post(f"{BASE_URL}/auth/forgot-password", json={
        "email": "test@example.com"
    }, timeout=10)
    assert resp.status_code in (200, 422)


def test_refresh_token_endpoint_exists(token):
    resp = requests.post(f"{BASE_URL}/auth/refresh-token", json={
        "token": token
    }, timeout=10)
    assert resp.status_code in (200, 400, 401, 422)


def test_verify_email_endpoint_exists():
    resp = requests.post(f"{BASE_URL}/auth/verify-email", json={
        "token": "invalid-token"
    }, timeout=10)
    assert resp.status_code in (200, 400, 422)


def test_register_endpoint_exists():
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "name": "Test", "email": "nope@nope.com", "password": "short"
    }, timeout=10)
    assert resp.status_code in (200, 201, 400, 422)
