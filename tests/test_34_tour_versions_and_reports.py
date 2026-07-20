"""Module 34 - Tour Versions and Reports"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

# Use well-known tour IDs; skip gracefully if they don't exist
_TOUR_ID = 1


def _get_first_tour_id(headers) -> int:
    resp = requests.get(f"{BASE_URL}/tours", headers=headers, timeout=10)
    if resp.status_code == 200:
        body = resp.json()
        items = body if isinstance(body, list) else body.get("data", body.get("items", []))
        if items:
            return items[0].get("id") or items[0].get("tour_id") or 1
    return 1


# ─── Tour Versions ────────────────────────────────────────────────────────────

def test_tour_versions_returns_200_or_404(headers):
    tour_id = _get_first_tour_id(headers)
    resp = requests.get(
        f"{BASE_URL}/tours/{tour_id}/versions",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 404), (
        f"Expected 200 or 404 for tour versions, got {resp.status_code}: {resp.text}"
    )


def test_tour_versions_is_list_when_200(headers):
    tour_id = _get_first_tour_id(headers)
    resp = requests.get(
        f"{BASE_URL}/tours/{tour_id}/versions",
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 404:
        pytest.skip(f"Tour {tour_id} not found")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of versions, got: {type(items)}"


def test_approve_nonexistent_tour_version(headers):
    resp = requests.patch(
        f"{BASE_URL}/tours/999999/versions/999999/approve",
        headers=headers,
        json={},
        timeout=10,
    )
    assert resp.status_code == 404, (
        f"Expected 404 for non-existent tour version approve, "
        f"got {resp.status_code}: {resp.text}"
    )


def test_reject_nonexistent_tour_version(headers):
    resp = requests.patch(
        f"{BASE_URL}/tours/999999/versions/999999/reject",
        headers=headers,
        json={"rejection_reason": "test rejection"},
        timeout=10,
    )
    assert resp.status_code in (404, 422), (
        f"Expected 404 or 422 for non-existent tour version reject, "
        f"got {resp.status_code}: {resp.text}"
    )


# ─── Reports Summary ──────────────────────────────────────────────────────────

def test_reports_summary_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/summary", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_summary_has_expected_keys(headers):
    resp = requests.get(f"{BASE_URL}/reports/summary", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data", body)
    # At least one of the standard summary keys should be present
    expected_keys = {
        "total_bookings", "total_revenue", "bookings", "revenue",
        "total_customers", "customers", "total_tours", "tours",
    }
    present = expected_keys & set(data.keys())
    assert present, (
        f"Expected at least one of {expected_keys} in reports/summary, got: {list(data.keys())}"
    )


# ─── Individual Report Endpoints ──────────────────────────────────────────────

def test_reports_bookings_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/bookings", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_payments_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/payments", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_agents_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/agents", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_suppliers_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/suppliers", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_customers_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/customers", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_cancellations_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/cancellations", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_country_wise_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/country-wise", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_overdue_payments_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/overdue-payments", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_pending_payments_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/pending-payments", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_exports_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/reports/exports", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


# ─── Activity Logs ────────────────────────────────────────────────────────────

def test_activity_logs_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/activity-logs", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_activity_logs_is_list(headers):
    resp = requests.get(f"{BASE_URL}/activity-logs", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of activity logs, got: {type(items)}"


def test_activity_logs_export_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/activity-logs/export", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_reports_require_auth():
    resp = requests.get(f"{BASE_URL}/reports/summary", timeout=10)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 without auth for reports, got {resp.status_code}: {resp.text}"
    )


def test_activity_logs_require_auth():
    resp = requests.get(f"{BASE_URL}/activity-logs", timeout=10)
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 without auth for activity-logs, got {resp.status_code}: {resp.text}"
    )
