import requests
from conftest import BASE_URL


def test_booking_communications_endpoint_requires_existing_booking(headers):
    resp = requests.post(f"{BASE_URL}/bookings/0/communications", json={"subject": "Test", "message": "Hello"}, headers=headers, timeout=10)
    assert resp.status_code in {403, 404}, resp.text
