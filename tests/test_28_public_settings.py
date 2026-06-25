"""Module 28 — Public Settings (no auth required)"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

# Sensitive keys that must NOT be exposed publicly
_SENSITIVE_KEYS = {
    "stripe_secret_key",
    "stripe_public_key",
    "stripe_webhook_secret",
    "payment_gateway_secret",
    "smtp_password",
    "secret_key",
}


def test_public_settings_returns_200():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text


def test_public_settings_has_data_key():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Response can be {"data": {...}} or the dict directly
    data = body.get("data", body)
    assert isinstance(data, dict), f"Expected dict for public settings, got: {type(data)}"


def test_public_settings_has_currency():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    assert "currency" in data or "default_currency" in data, (
        f"Expected 'currency' key in public settings, got keys: {list(data.keys())}"
    )


def test_public_settings_has_site_name():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    assert "site_name" in data or "app_name" in data or "company_name" in data, (
        f"Expected 'site_name' key in public settings, got keys: {list(data.keys())}"
    )


def test_public_settings_has_support_email():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    assert "support_email" in data or "contact_email" in data or "email" in data, (
        f"Expected support email key in public settings, got keys: {list(data.keys())}"
    )


def test_public_settings_does_not_expose_stripe_secret_key():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    assert "stripe_secret_key" not in data, (
        "stripe_secret_key must NOT be exposed in public settings"
    )


def test_public_settings_does_not_expose_stripe_public_key():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    assert "stripe_public_key" not in data, (
        "stripe_public_key must NOT be exposed in public settings"
    )


def test_public_settings_no_sensitive_keys():
    resp = requests.get(f"{BASE_URL}/settings/public", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    leaked = _SENSITIVE_KEYS & set(data.keys())
    assert not leaked, f"Sensitive keys exposed in public settings: {leaked}"


def test_client_config_returns_200():
    resp = requests.get(f"{BASE_URL}/client/config", timeout=10)
    assert resp.status_code == 200, resp.text


def test_client_config_has_body():
    resp = requests.get(f"{BASE_URL}/client/config", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None, "client/config returned null body"
    data = body.get("data", body)
    assert isinstance(data, dict), f"Expected dict from client/config, got: {type(data)}"
