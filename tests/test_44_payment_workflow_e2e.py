"""Module 44 - End-to-end payment workflow (Stripe test mode + local simulate).

Validates: full payment, deposit + remaining balance, refund, real Stripe
test-mode checkout-session creation, and agent "Reserve Now" (no deposit)
auto-invoice generation. These are pytest.ini's requests-based / live-server
integration tests, same convention as the rest of this suite.
"""
import pytest
import requests

from tests.conftest import BASE_URL, skip_if_readonly


def _create_booking(headers, tour_id, payment_type="full", extra=None):
    payload = {
        "customer_id": 1, "tour_id": tour_id, "tour_name": "Payment Workflow Test",
        "tour_date": "2027-06-01", "tour_start_date": "2027-06-01",
        "no_of_adults": 1, "no_of_children": 0, "currency": "USD",
        "booking_source": "customer", "payment_type": payment_type,
        "travellers": [{"traveller_type": "adult", "full_name": "Payment Workflow Traveller", "age": 30, "email": "paymentworkflow@example.com", "phone": "+911234500000", "is_primary_contact": True}],
    }
    if extra:
        payload.update(extra)
    return requests.post(f"{BASE_URL}/bookings", json=payload, headers=headers, timeout=30)


def _booking_or_skip(headers, tour_id, payment_type="full", extra=None):
    response = _create_booking(headers, tour_id, payment_type, extra)
    if response.status_code not in (200, 201):
        pytest.skip(f"No bookable pricing/calendar fixture: {response.status_code} {response.text[:200]}")
    return response.json()["data"]


@skip_if_readonly()
def test_full_payment_marks_booking_paid(headers, first_tour_id):
    booking = _booking_or_skip(headers, first_tour_id, "full")
    amount = float(booking["amount_pending"])
    sim = requests.post(f"{BASE_URL}/payments/test/simulate", json={"booking_id": booking["id"], "amount": amount, "note": "full payment e2e"}, headers=headers, timeout=10)
    assert sim.status_code in (200, 201), sim.text
    detail = requests.get(f"{BASE_URL}/bookings/{booking['id']}", headers=headers, timeout=10).json()["data"]
    assert detail["payment_status"] == "paid"
    assert float(detail["amount_pending"]) == 0


@skip_if_readonly()
def test_deposit_then_remaining_balance_reaches_paid(headers, first_tour_id):
    booking = _booking_or_skip(headers, first_tour_id, "partial")
    total = float(booking["amount_pending"])
    deposit = round(total * 0.3, 2)
    sim1 = requests.post(f"{BASE_URL}/payments/test/simulate", json={"booking_id": booking["id"], "amount": deposit, "note": "deposit e2e"}, headers=headers, timeout=10)
    assert sim1.status_code in (200, 201), sim1.text
    mid = requests.get(f"{BASE_URL}/bookings/{booking['id']}", headers=headers, timeout=10).json()["data"]
    assert mid["payment_status"] == "partially_paid"
    remaining = float(mid["amount_pending"])
    sim2 = requests.post(f"{BASE_URL}/payments/test/simulate", json={"booking_id": booking["id"], "amount": remaining, "note": "remaining balance e2e"}, headers=headers, timeout=10)
    assert sim2.status_code in (200, 201), sim2.text
    final = requests.get(f"{BASE_URL}/bookings/{booking['id']}", headers=headers, timeout=10).json()["data"]
    assert final["payment_status"] == "paid"


@skip_if_readonly()
def test_refund_reverts_paid_booking(headers, first_tour_id):
    booking = _booking_or_skip(headers, first_tour_id, "full")
    amount = float(booking["amount_pending"])
    requests.post(f"{BASE_URL}/payments/test/simulate", json={"booking_id": booking["id"], "amount": amount, "note": "refund e2e setup"}, headers=headers, timeout=10)
    payments = requests.get(f"{BASE_URL}/payments", headers=headers, params={"booking_id": booking["id"]}, timeout=10).json().get("items", [])
    assert payments
    refund = requests.post(f"{BASE_URL}/payments/{payments[0]['id']}/refund", json={"amount": amount, "reason": "e2e refund test"}, headers=headers, timeout=10)
    assert refund.status_code in (200, 201), refund.text
    detail = requests.get(f"{BASE_URL}/bookings/{booking['id']}", headers=headers, timeout=10).json()["data"]
    assert detail["payment_status"] == "refunded"


@skip_if_readonly()
def test_stripe_create_session_returns_real_checkout_url(headers, first_tour_id):
    """Confirms the configured Stripe keys are valid test-mode credentials by
    actually creating a checkout session (never completed/charged)."""
    gw = requests.get(f"{BASE_URL}/payments/gateways/status", headers=headers, timeout=10).json().get("data", {})
    if not gw.get("stripe"):
        return  # Stripe not configured in this environment
    booking = _booking_or_skip(headers, first_tour_id, "full")
    session = requests.post(f"{BASE_URL}/payments/stripe/create-session", json={
        "booking_id": booking["id"], "amount": float(booking["amount_pending"]), "currency": booking.get("currency", "USD"),
        "payment_type": "full",
        "success_url": "https://example.com/success", "cancel_url": "https://example.com/cancel",
    }, headers=headers, timeout=15)
    assert session.status_code in (200, 201), session.text
    assert "checkout.stripe.com" in session.json()["data"]["checkout_url"]


@skip_if_readonly()
def test_agent_reserve_now_generates_invoice_without_payment(headers, first_tour_id):
    agents = requests.get(f"{BASE_URL}/agents", headers=headers, params={"limit": 1}, timeout=10).json().get("items", [])
    if not agents:
        return
    booking = _booking_or_skip(headers, first_tour_id, "full", extra={
        "booking_source": "agent", "agent_id": agents[0]["id"], "agent_payment_method": "pay_later",
    })
    assert booking["payment_status"] == "credit_approval_pending"
    invoices = requests.get(f"{BASE_URL}/invoices", headers=headers, params={"booking_id": booking["id"]}, timeout=10).json().get("items", [])
    assert len(invoices) > 0


@skip_if_readonly()
def test_paid_booking_acceptance_creates_supplier_ledger(headers, first_tour_id):
    suppliers_response = requests.get(
        f"{BASE_URL}/suppliers", headers=headers, params={"limit": 20}, timeout=10
    )
    assert suppliers_response.status_code == 200, suppliers_response.text
    suppliers_body = suppliers_response.json()
    suppliers = suppliers_body.get("items", suppliers_body.get("data", []))
    active = next(
        (
            supplier
            for supplier in suppliers
            if supplier.get("status") == "active"
            and str(supplier.get("approval_status", "")).lower() in {"approved", "not_required"}
        ),
        None,
    )
    if not active:
        pytest.skip("No approved active supplier fixture is available")

    booking = _booking_or_skip(headers, first_tour_id, "full")
    booking_id = booking["id"]
    supplier_id = active["id"]

    assigned = requests.post(
        f"{BASE_URL}/bookings/{booking_id}/assign-supplier",
        json={"supplier_id": supplier_id, "reason": "payment workflow e2e"},
        headers=headers,
        timeout=10,
    )
    assert assigned.status_code == 200, assigned.text

    amount = float(assigned.json()["data"]["amount_pending"])
    paid = requests.post(
        f"{BASE_URL}/payments/test/simulate",
        json={"booking_id": booking_id, "amount": amount, "note": "acceptance ledger e2e"},
        headers=headers,
        timeout=10,
    )
    assert paid.status_code in (200, 201), paid.text

    accepted = requests.post(
        f"{BASE_URL}/supplier/bookings/{booking_id}/accept",
        json={"reason": "accepted by payment workflow e2e"},
        headers=headers,
        timeout=10,
    )
    assert accepted.status_code == 200, accepted.text
    accepted_booking = accepted.json()["data"]
    assert accepted_booking["supplier_acceptance_status"] == "accepted"
    assert accepted_booking["booking_status"] == "supplier_accepted"

    ledger_response = requests.get(
        f"{BASE_URL}/suppliers/{supplier_id}/ledger",
        headers=headers,
        params={"limit": 100},
        timeout=10,
    )
    assert ledger_response.status_code == 200, ledger_response.text
    ledger_body = ledger_response.json()
    ledger_rows = ledger_body.get("items", ledger_body.get("data", []))
    assert any(row.get("booking_id") == booking_id for row in ledger_rows), ledger_body
