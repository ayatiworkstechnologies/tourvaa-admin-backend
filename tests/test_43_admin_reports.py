"""Module 43 - Row-level Admin Reports and Supplier Self-Service Reports

Covers the "first release" report set added on top of the existing
aggregate /reports/* endpoints: 7 admin reports (booking-report,
sales-revenue-report, payment-report, supplier-report,
supplier-payout-report, tour-performance-report,
cancellation-refund-report) and 3 supplier-scoped reports (my-bookings,
my-earnings, my-travellers). Admin reports must be admin-only (403 for a
supplier actor, mirroring the existing _require_admin_report pattern);
supplier reports must be scoped to the caller's own supplier and 403 for a
non-supplier actor.
"""
import pytest
import requests

from tests.conftest import BASE_URL, create_active_account, login_with_retry, unique, unique_phone

ADMIN_REPORT_PATHS = [
    "booking-report",
    "sales-revenue-report",
    "payment-report",
    "supplier-report",
    "supplier-payout-report",
    "tour-performance-report",
    "cancellation-refund-report",
]

SUPPLIER_REPORT_PATHS = ["my-bookings", "my-earnings", "my-travellers"]


@pytest.mark.parametrize("path", ADMIN_REPORT_PATHS)
def test_admin_report_loads_for_admin(headers, path):
    resp = requests.get(f"{BASE_URL}/reports/{path}", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert "data" in body


@pytest.mark.parametrize("path", ADMIN_REPORT_PATHS)
def test_admin_report_requires_auth(path):
    resp = requests.get(f"{BASE_URL}/reports/{path}", timeout=10)
    assert resp.status_code in (401, 403)


@pytest.fixture(scope="module")
def supplier_report_ctx(headers):
    name = f"Report Test Supplier {unique('n')}"
    email = f"{unique('reportsup')}@example.com"
    password = "RepSup@1234"
    create_active_account("supplier", "SUPPLIER", name, email, unique_phone(), password)

    search = requests.get(f"{BASE_URL}/suppliers", params={"search": name, "limit": 10}, headers=headers, timeout=10)
    assert search.status_code == 200, search.text
    items = search.json().get("items", [])
    match = next((s for s in items if s.get("name") == name or s.get("supplier_name") == name), None)
    assert match, f"Newly created supplier {name!r} not found via admin search"
    supplier_id = match["id"]

    approve = requests.post(f"{BASE_URL}/suppliers/{supplier_id}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text

    login = login_with_retry(email, password)
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "supplier_id": supplier_id}


@pytest.mark.parametrize("path", ADMIN_REPORT_PATHS)
def test_admin_report_rejects_supplier_actor(supplier_report_ctx, path):
    resp = requests.get(f"{BASE_URL}/reports/{path}", headers=supplier_report_ctx["headers"], timeout=10)
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("path", SUPPLIER_REPORT_PATHS)
def test_supplier_report_loads_for_supplier(supplier_report_ctx, path):
    resp = requests.get(f"{BASE_URL}/reports/{path}", headers=supplier_report_ctx["headers"], timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert "data" in body


@pytest.mark.parametrize("path", SUPPLIER_REPORT_PATHS)
def test_supplier_report_rejects_admin_actor(headers, path):
    # The admin account has no linked Supplier profile, so it must be
    # rejected the same way any non-supplier caller would be.
    resp = requests.get(f"{BASE_URL}/reports/{path}", headers=headers, timeout=10)
    assert resp.status_code == 403, resp.text


def test_supplier_report_scoped_to_own_supplier_only(headers, supplier_report_ctx):
    # A second, independent supplier must never see the first supplier's
    # booking rows via my-bookings - each fixture only ever queries its own
    # supplier_id, so an empty-but-200 response for a fresh supplier with no
    # bookings is itself the scoping proof (no cross-tenant leakage).
    name = f"Report Test Supplier {unique('n2')}"
    email = f"{unique('reportsup2')}@example.com"
    password = "RepSup@1234"
    create_active_account("supplier", "SUPPLIER", name, email, unique_phone(), password)
    search = requests.get(f"{BASE_URL}/suppliers", params={"search": name, "limit": 10}, headers=headers, timeout=10)
    items = search.json().get("items", [])
    match = next((s for s in items if s.get("name") == name or s.get("supplier_name") == name), None)
    assert match
    approve = requests.post(f"{BASE_URL}/suppliers/{match['id']}/approve", headers=headers, timeout=10)
    assert approve.status_code == 200, approve.text
    login = login_with_retry(email, password)
    token = login.json()["data"]["access_token"]
    second_headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(f"{BASE_URL}/reports/my-bookings", headers=second_headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == [], "A brand-new supplier must not see any bookings, including another supplier's"


def test_sales_revenue_report_has_expected_keys(headers):
    resp = requests.get(f"{BASE_URL}/reports/sales-revenue-report", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    for key in ["total_bookings", "gross_booking_value", "discounts", "taxes", "platform_commission", "supplier_payable", "refund_amount", "net_platform_revenue", "time_series"]:
        assert key in data, f"Missing key {key!r} in sales-revenue-report response"


def test_sales_revenue_report_rejects_invalid_granularity(headers):
    resp = requests.get(f"{BASE_URL}/reports/sales-revenue-report", params={"granularity": "yearly"}, headers=headers, timeout=10)
    assert resp.status_code == 400, resp.text


def test_tour_performance_report_marks_views_not_tracked(headers):
    resp = requests.get(f"{BASE_URL}/reports/tour-performance-report", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    if data:
        assert data[0]["views"] == "Not tracked"
        assert data[0]["enquiries"] == "Not tracked"


@pytest.mark.parametrize("path", ADMIN_REPORT_PATHS + SUPPLIER_REPORT_PATHS)
def test_report_registered_for_csv_export(path):
    from app.routers.reports import REPORT_FETCHERS, REPORT_LABELS
    assert path in REPORT_FETCHERS
    assert path in REPORT_LABELS


def test_admin_can_export_new_report_as_csv(headers):
    resp = requests.get(f"{BASE_URL}/reports/exports", params={"report": "booking-report", "format": "csv"}, headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type", "").startswith("text/csv")


def test_supplier_can_export_own_report_as_csv(supplier_report_ctx):
    resp = requests.get(f"{BASE_URL}/reports/exports", params={"report": "my-earnings", "format": "csv"}, headers=supplier_report_ctx["headers"], timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type", "").startswith("text/csv")
