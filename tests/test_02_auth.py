"""Module 02 - Authentication"""
import pytest
import requests
from tests.conftest import BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD, skip_if_readonly


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
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL, "password": "WrongPassword"
    }, timeout=10)
    assert resp.status_code in (400, 401, 422)


def test_login_invalid_email():
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "notexist@example.com", "password": "any"
    }, timeout=10)
    assert resp.status_code in (400, 401, 422)


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
