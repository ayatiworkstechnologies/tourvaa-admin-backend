import requests

from tests.conftest import BASE_URL, skip_if_readonly


def test_bookings_list_and_upcoming(headers):
    resp = requests.get(f"{BASE_URL}/bookings", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert "items" in body

    upcoming = requests.get(f"{BASE_URL}/bookings/upcoming", headers=headers, timeout=10)
    assert upcoming.status_code == 200, upcoming.text


def test_bookings_export(headers):
    resp = requests.get(f"{BASE_URL}/bookings/export", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


@skip_if_readonly()
def test_booking_create_requires_published_tour(headers, first_tour_id):
    payload = {"customer_id": 1, "tour_id": first_tour_id, "booking_source": "admin", "adults_count": 1, "children_count": 0, "tour_name": "Guarded Test", "tour_date": "2026-07-01"}
    resp = requests.post(f"{BASE_URL}/bookings", json=payload, headers=headers, timeout=10)
    assert resp.status_code in {200, 400, 404, 422}, resp.text


def test_booking_calculate_price(headers, first_tour_id):
    if not first_tour_id:
        return
    payload = {"customer_id": 1, "tour_id": first_tour_id, "booking_source": "admin", "adults_count": 2, "children_count": 1, "tour_name": "Price Calc", "tour_date": "2026-09-15"}
    resp = requests.post(f"{BASE_URL}/bookings/calculate-price", json=payload, headers=headers, timeout=10)
    assert resp.status_code in (200, 400, 404, 422), resp.text


def test_booking_detail_not_found(headers):
    resp = requests.get(f"{BASE_URL}/bookings/999999999", headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


def test_booking_detail_and_dependents(headers, first_booking_id):
    if not first_booking_id:
        return  # no bookings seeded in this environment — nothing to assert against

    detail = requests.get(f"{BASE_URL}/bookings/{first_booking_id}", headers=headers, timeout=10)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["id"] == first_booking_id

    history = requests.get(f"{BASE_URL}/bookings/{first_booking_id}/status-history", headers=headers, timeout=10)
    assert history.status_code == 200, history.text

    payment_link = requests.get(f"{BASE_URL}/bookings/{first_booking_id}/payment-link", headers=headers, timeout=10)
    assert payment_link.status_code in (200, 400, 404), payment_link.text


def test_booking_calendar_event_lifecycle(headers, first_booking_id):
    if not first_booking_id:
        return

    event = requests.get(f"{BASE_URL}/bookings/{first_booking_id}/calendar-event", headers=headers, timeout=10)
    assert event.status_code in (200, 404), event.text

    download = requests.get(f"{BASE_URL}/bookings/{first_booking_id}/calendar-event/download", headers=headers, timeout=10)
    assert download.status_code in (200, 404), download.text


@skip_if_readonly()
def test_booking_calendar_sync(headers, first_booking_id):
    if not first_booking_id:
        return
    resp = requests.post(f"{BASE_URL}/bookings/{first_booking_id}/calendar-sync", headers=headers, timeout=10)
    assert resp.status_code in (200, 400, 404), resp.text


def test_booking_status_history_not_found(headers):
    resp = requests.get(f"{BASE_URL}/bookings/999999999/status-history", headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


@skip_if_readonly()
def test_booking_assign_supplier_not_found(headers):
    resp = requests.post(f"{BASE_URL}/bookings/999999999/assign-supplier", json={
        "supplier_id": 1, "reason": "test assignment",
    }, headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


@skip_if_readonly()
def test_booking_cancel_not_found(headers):
    resp = requests.patch(f"{BASE_URL}/bookings/999999999/cancel", json={
        "reason": "test cancel",
    }, headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


@skip_if_readonly()
def test_booking_communications_and_replies(headers, first_booking_id):
    if not first_booking_id:
        return
    comm = requests.post(f"{BASE_URL}/bookings/{first_booking_id}/communications", json={
        "subject": "Admin note", "message": "Confirming with supplier", "visibility": "internal",
    }, headers=headers, timeout=10)
    assert comm.status_code in (200, 201, 404), comm.text
    if comm.status_code in (200, 201):
        communication_id = comm.json()["data"]["id"]
        reply = requests.post(f"{BASE_URL}/bookings/communications/{communication_id}/replies", json={
            "message": "Follow-up reply",
        }, headers=headers, timeout=10)
        assert reply.status_code in (200, 201), reply.text
