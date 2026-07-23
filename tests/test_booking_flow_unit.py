from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.bookings import (
    _booking_seat_count,
    _price_booking,
    _start_supplier_decision,
    _validate_booking_status_transition,
    _validate_customer_travellers,
    _validate_supplier_lifecycle_transition,
)
from app.services.payments import _derive_booking_status, _ensure_payment_access, _status_after_payment_sync
from app.routers.payments_gateway import _ensure_booking_payment_access, _validate_payment_currency, _validate_payment_request
from app.schemas.bookings import BookingCreate, BookingTravellerPayload
from app.schemas.agents import AgentSelfUpdate
from app.schemas.suppliers import SupplierSelfUpdate
from app.services.agent_scope import is_agent_user
from app.services.supplier_scope import is_supplier_user, reject_supplier_review_action


def booking(**overrides):
    values = {
        "booking_status": "payment_authorized",
        "supplier_id": 10,
        "supplier_acceptance_status": "pending",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_supplier_self_update_rejects_admin_managed_fields():
    with pytest.raises(ValidationError):
        SupplierSelfUpdate(status="active")


def test_supplier_role_is_scoped_and_cannot_review_tours():
    user = SimpleNamespace(role=SimpleNamespace(slug="supplier"), user_roles=[])
    assert is_supplier_user(user) is True
    with pytest.raises(HTTPException) as exc:
        reject_supplier_review_action(user)
    assert exc.value.status_code == 403


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


@pytest.mark.parametrize(("current", "target"), [("confirmed", "ongoing"), ("postponed", "ongoing"), ("ongoing", "completed"), ("confirmed", "completed")])
def test_supplier_lifecycle_allows_valid_execution_transitions(current, target):
    row = booking(booking_status=current, supplier_acceptance_status="accepted")
    assert _validate_supplier_lifecycle_transition(row, target) is True


def test_supplier_lifecycle_retry_is_idempotent():
    row = booking(booking_status="completed", supplier_acceptance_status="accepted")
    assert _validate_supplier_lifecycle_transition(row, "completed") is False


def test_supplier_lifecycle_requires_acceptance():
    row = booking(booking_status="confirmed", supplier_acceptance_status="pending")
    with pytest.raises(HTTPException) as exc:
        _validate_supplier_lifecycle_transition(row, "ongoing")
    assert exc.value.status_code == 409


def test_supplier_lifecycle_rejects_invalid_source_status():
    row = booking(booking_status="pending_payment", supplier_acceptance_status="accepted")
    with pytest.raises(HTTPException) as exc:
        _validate_supplier_lifecycle_transition(row, "completed")
    assert exc.value.status_code == 400


def test_admin_booking_status_transition_allows_forward_progress():
    assert _validate_booking_status_transition("confirmed", "ongoing") is True


def test_admin_booking_status_transition_is_idempotent():
    assert _validate_booking_status_transition("confirmed", "confirmed") is False


def test_admin_booking_status_transition_rejects_terminal_reversal():
    with pytest.raises(HTTPException) as exc:
        _validate_booking_status_transition("completed", "pending_payment")
    assert exc.value.status_code == 409


def test_total_travellers_includes_infants_but_seat_count_does_not():
    data = BookingCreate(
        customer_id=1,
        booking_source="admin",
        no_of_adults=2,
        no_of_children=1,
        no_of_infants=1,
    )
    priced = _price_booking(None, data)
    assert priced[4] == 4
    row = SimpleNamespace(adults_count=2, children_count=1, no_of_adults=2, no_of_children=1)
    assert _booking_seat_count(row) == 3


def payment_booking(**overrides):
    values = {
        "booking_status": "pending_payment",
        "amount_pending": "1000.00",
        "currency": "USD",
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


def test_gateway_requires_the_immutable_booking_currency():
    assert _validate_payment_currency(payment_booking(), "usd") == "USD"
    with pytest.raises(HTTPException) as exc:
        _validate_payment_currency(payment_booking(), "INR")
    assert exc.value.status_code == 400


def test_gateway_rejects_payment_from_another_customer():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(payment_booking(), "300.00", customer_user(99))
    assert exc.value.status_code == 403


def test_agent_can_pay_booking_created_by_own_agent_profile():
    row = payment_booking(agent=SimpleNamespace(user_id=77))
    actor = SimpleNamespace(id=77, role=SimpleNamespace(slug="agent-reseller"))
    _ensure_booking_payment_access(row, actor)


def test_agent_cannot_pay_another_agents_booking():
    row = payment_booking(agent=SimpleNamespace(user_id=77))
    actor = SimpleNamespace(id=88, role=SimpleNamespace(slug="agent-reseller"))
    with pytest.raises(HTTPException) as exc:
        _ensure_booking_payment_access(row, actor)
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


def test_agent_traveller_manifest_matches_selected_counts():
    data = BookingCreate(
        customer_id=1,
        agent_id=7,
        booking_source="agent",
        no_of_adults=1,
        no_of_children=1,
        travellers=[
            BookingTravellerPayload(traveller_type="adult", full_name="Adult One", age=35, is_primary_contact=True),
            BookingTravellerPayload(traveller_type="child", full_name="Child One", age=8),
        ],
    )
    _validate_customer_travellers(data, adults=1, children=1)


def test_agent_traveller_manifest_is_required():
    data = BookingCreate(customer_id=1, agent_id=7, booking_source="agent", no_of_adults=1)
    with pytest.raises(HTTPException) as exc:
        _validate_customer_travellers(data, adults=1, children=0)
    assert exc.value.status_code == 400


def test_agent_self_update_rejects_admin_only_fields():
    with pytest.raises(ValidationError):
        AgentSelfUpdate(agent_name="Safe Agency", status="active")


def test_agent_role_detection_handles_agent_reseller():
    actor = SimpleNamespace(role=SimpleNamespace(slug="agent-reseller"))
    assert is_agent_user(actor) is True
