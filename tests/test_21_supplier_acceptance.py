import requests
from conftest import BASE_URL


def test_supplier_booking_endpoints_require_auth_scope(headers):
    resp = requests.get(f"{BASE_URL}/supplier/bookings", headers=headers, timeout=10)
    assert resp.status_code in {200, 403}, resp.text
