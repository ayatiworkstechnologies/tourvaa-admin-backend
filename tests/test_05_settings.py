"""Module 05 — Settings"""
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly


def test_system_settings_get(headers):
    resp = requests.get(f"{BASE_URL}/settings/system", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_payment_settings_get(headers):
    resp = requests.get(f"{BASE_URL}/settings/payment", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_api_settings_get(headers):
    resp = requests.get(f"{BASE_URL}/settings/api", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_payment_settings_summary(headers):
    resp = requests.get(f"{BASE_URL}/settings/payment/summary", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_api_settings_summary(headers):
    resp = requests.get(f"{BASE_URL}/settings/api/summary", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_settings_require_auth():
    resp = requests.get(f"{BASE_URL}/settings/system", timeout=10)
    assert resp.status_code in (401, 403)


@skip_if_readonly()
def test_system_settings_update(headers):
    resp = requests.put(f"{BASE_URL}/settings/system", headers=headers, json={
        "app_name": "Tourvaa Test", "app_timezone": "Asia/Kolkata"
    }, timeout=10)
    assert resp.status_code in (200, 201, 204)


@skip_if_readonly()
def test_payment_settings_update(headers):
    resp = requests.put(f"{BASE_URL}/settings/payment", headers=headers, json={}, timeout=10)
    assert resp.status_code in (200, 201, 204, 422)


@skip_if_readonly()
def test_api_settings_update(headers):
    resp = requests.put(f"{BASE_URL}/settings/api", headers=headers, json={}, timeout=10)
    assert resp.status_code in (200, 201, 204, 422)
