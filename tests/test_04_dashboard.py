"""Module 04 — Dashboard"""
import pytest
import requests
from tests.conftest import BASE_URL


def test_dashboard_me(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_summary(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_summary_required_fields(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    body = resp.json()
    data = body.get("data", body)
    for field in ["total_bookings", "total_customers", "total_suppliers", "total_agents"]:
        assert field in data, f"summary missing field: {field}"


def test_dashboard_summary_no_crash_with_filters(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary?start_date=2024-01-01&end_date=2024-12-31",
                        headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_summary_country_filter(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary?country_id=1",
                        headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_bookings(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/bookings", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_revenue(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/revenue", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_payments(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/payments", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_recent_activities(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/recent-activities", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_summary_zero_safe(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    data = resp.json().get("data", resp.json())
    assert isinstance(data.get("total_bookings", 0), (int, float))
    assert isinstance(data.get("total_customers", 0), (int, float))


def test_dashboard_no_v1_reference(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    assert resp.status_code != 404
