import requests

from tests.conftest import BASE_URL, skip_if_readonly


def test_payments_list(headers):
    resp = requests.get(f"{BASE_URL}/payments", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


def test_payments_gateways_status(headers):
    resp = requests.get(f"{BASE_URL}/payments/gateways/status", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_payment_detail_not_found(headers):
    resp = requests.get(f"{BASE_URL}/payments/999999999", headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


def test_customer_payment_list(headers):
    resp = requests.get(f"{BASE_URL}/payments/customer/1", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


@skip_if_readonly()
def test_payment_authorize_requires_valid_booking(headers):
    resp = requests.post(f"{BASE_URL}/payments/authorize", json={
        "booking_id": 999999999, "amount": 100, "payment_method": "card",
    }, headers=headers, timeout=10)
    assert resp.status_code in (400, 404, 422), resp.text


@skip_if_readonly()
def test_payment_capture_void_refund_not_found(headers):
    capture = requests.post(f"{BASE_URL}/payments/999999999/capture", json={
        "amount": 100,
    }, headers=headers, timeout=10)
    assert capture.status_code == 404, capture.text

    void = requests.post(f"{BASE_URL}/payments/999999999/void", json={
        "reason": "test void",
    }, headers=headers, timeout=10)
    assert void.status_code == 404, void.text

    refund = requests.post(f"{BASE_URL}/payments/999999999/refund", json={
        "amount": 50, "reason": "test refund",
    }, headers=headers, timeout=10)
    assert refund.status_code == 404, refund.text


@skip_if_readonly()
def test_payment_status_update_not_found(headers):
    resp = requests.patch(f"{BASE_URL}/payments/999999999/status", json={
        "payment_status": "paid",
    }, headers=headers, timeout=10)
    assert resp.status_code == 404, resp.text


@skip_if_readonly()
def test_payment_test_simulate_end_to_end(headers, first_booking_id):
    if not first_booking_id:
        return  # no booking to attach a simulated payment to in this environment
    resp = requests.post(f"{BASE_URL}/payments/test/simulate", json={
        "booking_id": first_booking_id, "amount": 100, "note": "pytest simulated payment",
    }, headers=headers, timeout=10)
    # 403 in production per the endpoint's own guard; otherwise should succeed.
    assert resp.status_code in (200, 201, 403), resp.text
    if resp.status_code in (200, 201):
        payment_id = resp.json().get("data", {}).get("id")
        if payment_id:
            detail = requests.get(f"{BASE_URL}/payments/{payment_id}", headers=headers, timeout=10)
            assert detail.status_code == 200, detail.text
