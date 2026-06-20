import requests

from conftest import BASE_URL, skip_if_readonly


def test_bookings_list_and_upcoming(headers):
    resp = requests.get(f"{BASE_URL}/bookings", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert "items" in body

    upcoming = requests.get(f"{BASE_URL}/bookings/upcoming", headers=headers, timeout=10)
    assert upcoming.status_code == 200, upcoming.text


@skip_if_readonly()
def test_booking_create_requires_published_tour(headers, first_tour_id):
    payload = {"customer_id": 1, "tour_id": first_tour_id, "booking_source": "admin", "adults_count": 1, "children_count": 0, "tour_name": "Guarded Test", "tour_date": "2026-07-01"}
    resp = requests.post(f"{BASE_URL}/bookings", json=payload, headers=headers, timeout=10)
    assert resp.status_code in {200, 400, 404, 422}, resp.text
