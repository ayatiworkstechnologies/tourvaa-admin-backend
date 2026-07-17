from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.bookings import _start_supplier_decision, _validate_customer_travellers
from app.services.payments import _derive_booking_status, _ensure_payment_access, _status_after_payment_sync
from app.routers.payments_gateway import _validate_payment_request
from app.schemas.bookings import BookingCreate, BookingTravellerPayload


def booking(**overrides):
    values = {
        "booking_status": "payment_authorized",
        "supplier_id": 10,
        "supplier_acceptance_status": "pending",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_paid_booking_waits_for_supplier_acceptance():
    row = booking()
    assert _status_after_payment_sync(row, "paid") == "pending_supplier_acceptance"


def test_paid_booking_confirms_after_supplier_acceptance():
    row = booking(supplier_acceptance_status="accepted")
    assert _status_after_payment_sync(row, "paid") == "confirmed"


def test_paid_unassigned_booking_can_confirm():
    row = booking(supplier_id=None, supplier_acceptance_status="not_assigned")
    assert _status_after_payment_sync(row, "paid") == "confirmed"


@pytest.mark.parametrize(
    ("net_paid", "final_amount", "expected"),
    [
        ("0", "1000", "unpaid"),
        ("300", "1000", "partially_paid"),
        ("1000", "1000", "paid"),
        ("1200", "1000", "paid"),
    ],
)
def test_payment_total_drives_payment_status(net_paid, final_amount, expected):
    assert _derive_booking_status(net_paid, final_amount) == expected


def test_partial_payment_does_not_advance_booking_status():
    row = booking(booking_status="pending_payment")
    assert _status_after_payment_sync(row, "partially_paid") is None


def test_paid_cancelled_booking_does_not_reopen():
    row = booking(booking_status="cancelled")
    assert _status_after_payment_sync(row, "paid") is None


def test_supplier_decision_retry_is_idempotent():
    row = booking(supplier_acceptance_status="accepted")
    assert _start_supplier_decision(row, "accepted") is False


def test_supplier_decision_cannot_be_reversed():
    row = booking(supplier_acceptance_status="accepted")
    with pytest.raises(HTTPException) as exc:
        _start_supplier_decision(row, "declined")
    assert exc.value.status_code == 409


def test_supplier_decision_requires_assignment():
    row = booking(supplier_id=None, supplier_acceptance_status="not_assigned")
    with pytest.raises(HTTPException) as exc:
        _start_supplier_decision(row, "accepted")
    assert exc.value.status_code == 400


def payment_booking(**overrides):
    values = {
        "booking_status": "pending_payment",
        "amount_pending": "1000.00",
        "customer": SimpleNamespace(user_id=42),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def customer_user(user_id=42):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(slug="customer"))


def test_gateway_accepts_partial_payment_within_outstanding_balance():
    amount = _validate_payment_request(payment_booking(), "300.00", customer_user())
    assert str(amount) == "300.00"


def test_gateway_rejects_overpayment():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(payment_booking(), "1000.01", customer_user())
    assert exc.value.status_code == 400


def test_gateway_rejects_payment_from_another_customer():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(payment_booking(), "300.00", customer_user(99))
    assert exc.value.status_code == 403


def test_gateway_rejects_cancelled_booking_payment():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(payment_booking(booking_status="cancelled"), "300.00", customer_user())
    assert exc.value.status_code == 409


def test_customer_cannot_read_another_customers_payment():
    payment = SimpleNamespace(
        customer=SimpleNamespace(user_id=42),
        booking=None,
    )
    actor = SimpleNamespace(id=99, role=SimpleNamespace(slug="customer"))
    with pytest.raises(HTTPException) as exc:
        _ensure_payment_access(payment, actor)
    assert exc.value.status_code == 403


def test_customer_can_read_own_payment():
    payment = SimpleNamespace(
        customer=SimpleNamespace(user_id=42),
        booking=None,
    )
    _ensure_payment_access(payment, customer_user())


def customer_booking_with_travellers(travellers):
    return BookingCreate(
        customer_id=1,
        booking_source="customer",
        no_of_adults=2,
        no_of_children=1,
        travellers=travellers,
    )


def test_customer_traveller_manifest_matches_selected_counts():
    data = customer_booking_with_travellers([
        BookingTravellerPayload(traveller_type="adult", full_name="Adult One", age=35, is_primary_contact=True),
        BookingTravellerPayload(traveller_type="adult", full_name="Adult Two", age=28),
        BookingTravellerPayload(traveller_type="child", full_name="Child One", age=8),
    ])
    _validate_customer_travellers(data, adults=2, children=1)


def test_customer_traveller_manifest_rejects_count_mismatch():
    data = customer_booking_with_travellers([
        BookingTravellerPayload(traveller_type="adult", full_name="Adult One", age=35, is_primary_contact=True),
        BookingTravellerPayload(traveller_type="child", full_name="Child One", age=8),
    ])
    with pytest.raises(HTTPException) as exc:
        _validate_customer_travellers(data, adults=2, children=1)
    assert exc.value.status_code == 400


def test_customer_traveller_manifest_rejects_invalid_child_age():
    data = customer_booking_with_travellers([
        BookingTravellerPayload(traveller_type="adult", full_name="Adult One", age=35, is_primary_contact=True),
        BookingTravellerPayload(traveller_type="adult", full_name="Adult Two", age=28),
        BookingTravellerPayload(traveller_type="child", full_name="Child One", age=14),
    ])
    with pytest.raises(HTTPException) as exc:
        _validate_customer_travellers(data, adults=2, children=1)
    assert exc.value.status_code == 400


def test_customer_traveller_manifest_requires_one_primary_contact():
    data = customer_booking_with_travellers([
        BookingTravellerPayload(traveller_type="adult", full_name="Adult One", age=35),
        BookingTravellerPayload(traveller_type="adult", full_name="Adult Two", age=28),
        BookingTravellerPayload(traveller_type="child", full_name="Child One", age=8),
    ])
    with pytest.raises(HTTPException) as exc:
        _validate_customer_travellers(data, adults=2, children=1)
    assert exc.value.status_code == 400
