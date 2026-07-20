"""
Module - Role-Based Dashboard Tests

Tests verify:
1. /api/dashboard/me returns required fields
2. /api/dashboard/summary returns role-scoped data
3. /api/dashboard/charts returns role-scoped chart data
4. /api/dashboard/recent-activities returns role-scoped activities
5. /api/dashboard/alerts returns role-scoped alerts
6. dashboard_type is correct for the logged-in role
7. Missing token returns 401
8. Ownership isolation (skipped if no role-specific users in DB)

All tests run against the live server (http://127.0.0.1:8000/api).
"""

import pytest
import requests
from tests.conftest import BASE_URL, get_admin_token, auth_headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_data(resp: requests.Response) -> dict:
    body = resp.json()
    return body.get("data", body)


# ---------------------------------------------------------------------------
# 1. GET /dashboard/me - Super Admin token
# ---------------------------------------------------------------------------

def test_dashboard_me_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_me_required_fields(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "user" in data, "missing 'user'"
    assert "permissions" in data, "missing 'permissions'"
    assert "menus" in data, "missing 'menus'"
    assert "dashboard_type" in data, "missing 'dashboard_type'"
    assert "allowed_modules" in data, "missing 'allowed_modules'"
    assert "sidebar_menu" in data, "missing 'sidebar_menu'"


def test_dashboard_me_user_fields(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    user = _get_data(resp).get("user", {})
    assert "id" in user
    assert "name" in user
    assert "email" in user
    assert "user_type" in user, "missing 'user_type' in user object"
    assert "role" in user


def test_dashboard_me_super_admin_dashboard_type(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    data = _get_data(resp)
    assert data["dashboard_type"] == "super_admin", (
        f"Expected 'super_admin', got '{data['dashboard_type']}'"
    )


def test_dashboard_me_allowed_modules_is_list(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    data = _get_data(resp)
    assert isinstance(data["allowed_modules"], list)


def test_dashboard_me_menus_have_required_keys(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/me", headers=headers, timeout=10)
    data = _get_data(resp)
    for menu in data.get("menus", []):
        assert "label" in menu, f"menu item missing 'label': {menu}"
        assert "module" in menu, f"menu item missing 'module': {menu}"


# ---------------------------------------------------------------------------
# 2. GET /dashboard/summary
# ---------------------------------------------------------------------------

def test_dashboard_summary_200(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_summary_admin_fields(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    data = _get_data(resp)
    required = ["total_bookings", "total_customers", "total_suppliers", "total_agents"]
    for field in required:
        assert field in data, f"summary missing field: {field}"


def test_dashboard_summary_with_filters(headers):
    resp = requests.get(
        f"{BASE_URL}/dashboard/summary?start_date=2024-01-01&end_date=2024-12-31",
        headers=headers, timeout=10,
    )
    assert resp.status_code == 200


def test_dashboard_summary_country_filter(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary?country_id=1", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_summary_numeric_values(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    data = _get_data(resp)
    assert isinstance(data.get("total_bookings", 0), (int, float))
    assert isinstance(data.get("total_customers", 0), (int, float))
    assert isinstance(data.get("total_suppliers", 0), (int, float))


def test_dashboard_summary_has_dashboard_type(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "dashboard_type" in data, "summary missing 'dashboard_type'"


# ---------------------------------------------------------------------------
# 3. GET /dashboard/charts
# ---------------------------------------------------------------------------

def test_dashboard_charts_200(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/charts", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_charts_has_booking_status(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/charts", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "booking_status_chart" in data, "charts missing 'booking_status_chart'"
    assert isinstance(data["booking_status_chart"], list)


def test_dashboard_charts_has_dashboard_type(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/charts", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "dashboard_type" in data


def test_dashboard_charts_with_filters(headers):
    resp = requests.get(
        f"{BASE_URL}/dashboard/charts?start_date=2024-01-01&end_date=2024-12-31",
        headers=headers, timeout=10,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. GET /dashboard/recent-activities
# ---------------------------------------------------------------------------

def test_dashboard_recent_activities_200(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/recent-activities", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_recent_activities_has_dashboard_type(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/recent-activities", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "dashboard_type" in data


def test_dashboard_recent_activities_admin_has_actions(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/recent-activities", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "recent_admin_actions" in data
    assert isinstance(data["recent_admin_actions"], list)


# ---------------------------------------------------------------------------
# 5. GET /dashboard/alerts
# ---------------------------------------------------------------------------

def test_dashboard_alerts_200(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/alerts", headers=headers, timeout=10)
    assert resp.status_code == 200


def test_dashboard_alerts_has_alerts_list(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/alerts", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "alerts" in data, "alerts response missing 'alerts' key"
    assert isinstance(data["alerts"], list)


def test_dashboard_alerts_has_dashboard_type(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/alerts", headers=headers, timeout=10)
    data = _get_data(resp)
    assert "dashboard_type" in data


# ---------------------------------------------------------------------------
# 6. Unauthenticated access returns 401
# ---------------------------------------------------------------------------

def test_dashboard_me_no_token_401():
    resp = requests.get(f"{BASE_URL}/dashboard/me", timeout=10)
    assert resp.status_code == 401


def test_dashboard_summary_no_token_401():
    resp = requests.get(f"{BASE_URL}/dashboard/summary", timeout=10)
    assert resp.status_code == 401


def test_dashboard_charts_no_token_401():
    resp = requests.get(f"{BASE_URL}/dashboard/charts", timeout=10)
    assert resp.status_code == 401


def test_dashboard_activities_no_token_401():
    resp = requests.get(f"{BASE_URL}/dashboard/recent-activities", timeout=10)
    assert resp.status_code == 401


def test_dashboard_alerts_no_token_401():
    resp = requests.get(f"{BASE_URL}/dashboard/alerts", timeout=10)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. No /api/v1 references
# ---------------------------------------------------------------------------

def test_dashboard_no_v1_path(headers):
    resp = requests.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=10)
    assert resp.status_code != 404
    assert "/v1/" not in resp.url


# ---------------------------------------------------------------------------
# 8. Supplier ownership isolation (skipped if no supplier user in DB)
# ---------------------------------------------------------------------------

def _get_supplier_token():
    """Try to get a token for a supplier user. Returns None if not available."""
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": "supplier@tourvaa.com", "password": "Supplier@123"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("data", {}).get("access_token") or data.get("access_token")
    except Exception:
        return None


def _get_customer_token():
    """Try to get a token for a customer user. Returns None if not available."""
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": "customer@tourvaa.com", "password": "Customer@123"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("data", {}).get("access_token") or data.get("access_token")
    except Exception:
        return None


def test_supplier_dashboard_type_if_exists():
    token = _get_supplier_token()
    if not token:
        pytest.skip("No supplier user in test DB (email: supplier@tourvaa.com)")

    resp = requests.get(
        f"{BASE_URL}/dashboard/me",
        headers=auth_headers(token),
        timeout=10,
    )
    assert resp.status_code == 200
    data = _get_data(resp)
    assert data["dashboard_type"] == "supplier", (
        f"Expected 'supplier', got '{data.get('dashboard_type')}'"
    )


def test_supplier_summary_scoped_to_own_data():
    token = _get_supplier_token()
    if not token:
        pytest.skip("No supplier user in test DB (email: supplier@tourvaa.com)")

    resp = requests.get(
        f"{BASE_URL}/dashboard/summary",
        headers=auth_headers(token),
        timeout=10,
    )
    assert resp.status_code == 200
    data = _get_data(resp)
    assert data.get("dashboard_type") == "supplier"
    # Supplier summary must not expose other suppliers' global totals
    assert "total_customers" not in data, "Supplier summary must not expose total_customers"
    assert "total_suppliers" not in data, "Supplier summary must not expose total_suppliers"


def test_customer_dashboard_type_if_exists():
    token = _get_customer_token()
    if not token:
        pytest.skip("No customer user in test DB (email: customer@tourvaa.com)")

    resp = requests.get(
        f"{BASE_URL}/dashboard/me",
        headers=auth_headers(token),
        timeout=10,
    )
    assert resp.status_code == 200
    data = _get_data(resp)
    assert data["dashboard_type"] == "customer"


def test_customer_summary_scoped_to_own_data():
    token = _get_customer_token()
    if not token:
        pytest.skip("No customer user in test DB (email: customer@tourvaa.com)")

    resp = requests.get(
        f"{BASE_URL}/dashboard/summary",
        headers=auth_headers(token),
        timeout=10,
    )
    assert resp.status_code == 200
    data = _get_data(resp)
    assert data.get("dashboard_type") == "customer"
    assert "total_suppliers" not in data, "Customer summary must not expose total_suppliers"
    assert "total_agents" not in data, "Customer summary must not expose total_agents"
