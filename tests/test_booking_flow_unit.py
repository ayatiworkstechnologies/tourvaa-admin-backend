from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.bookings import (
    _bookable_calendar_capacity,
    _booking_seat_count,
    _is_booking_fully_paid,
    _price_booking,
    _start_supplier_decision,
    _validate_booking_status_transition,
    _validate_customer_travellers,
    _validate_supplier_lifecycle_transition,
    create_booking,
)
from app.services.payments import _derive_booking_status, _ensure_payment_access, _status_after_payment_sync
from app.routers.payments_gateway import _ensure_booking_payment_access, _validate_payment_currency, _validate_payment_request
from app.schemas.bookings import BookingCreate, BookingTravellerPayload
from app.schemas.agents import AgentSelfUpdate
from app.schemas.agents import AgentInvoicingUpdate, AgentUpdate
from app.schemas.affiliates import AffiliateInvoicingUpdate, AffiliateUpdate
from app.schemas.suppliers import SupplierInvoicingUpdate, SupplierSelfUpdate, SupplierUpdate
from app.services.agent_scope import is_agent_user
from app.services.supplier_scope import is_supplier_user, reject_supplier_review_action
from app.services.suppliers import _mask_bank_identifier, update_supplier
from app.services.agents import update_agent
from app.services.affiliates import update_affiliate
# `_validate_payment_request` now takes (db, booking, amount, current_user)
# and falls back to the admin-configured platform deposit defaults
# (default_deposit_percentage / default_deposit_cutoff_days) when a tour has
# none of its own. These unit tests exercise the *tour-level* deposit rules,
# so neutralize the platform fallbacks to keep the original expectations
# (no tour deposit configured -> partial payment rejected) intact.
@pytest.fixture(autouse=True)
def _no_platform_deposit_defaults(monkeypatch):
    from app.routers import payments_gateway

    monkeypatch.setattr(payments_gateway, "get_default_deposit_cutoff_days", lambda db: None)
    monkeypatch.setattr(payments_gateway, "get_default_deposit_percentage", lambda db: None)


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


def test_supplier_bank_country_and_masked_identifiers_are_supported():
    """Suppliers retain a distinct bank country but never receive full saved IDs."""
    payload = SupplierInvoicingUpdate(bank_country_id=64, account_number="1234567890122323")
    assert payload.bank_country_id == 64
    assert _mask_bank_identifier(payload.account_number) == "************2323"
    assert _mask_bank_identifier("123") == "123"


class _DbCommitStub:
    def add(self, _item):
        pass

    def commit(self):
        pass

    def refresh(self, _item):
        pass


@pytest.mark.parametrize(
    ("service_path", "update", "invoicing", "record_name"),
    [
        ("app.services.agents", update_agent, AgentInvoicingUpdate(country_id=64), "agent"),
        ("app.services.affiliates", update_affiliate, AffiliateInvoicingUpdate(country_id=64), "affiliate"),
    ],
)
def test_locked_partner_bank_details_do_not_lock_billing_country(monkeypatch, service_path, update, invoicing, record_name):
    """Changing billing country must not be mistaken for editing bank credentials."""
    record = SimpleNamespace(
        id=7,
        user_id=41,
        invoicing=SimpleNamespace(
            preferred_payment_method="bank_transfer", account_name="Test", account_number="1234",
            bank_name="Bank", bank_branch="Branch", swift_code="", iban="", country_id=1,
        ),
        contacts=[], business_info=None, marketing_info=None,
    )
    monkeypatch.setattr(f"{service_path}.get_{record_name}", lambda _db, _id: record)
    monkeypatch.setattr(f"{service_path}.serialize_{record_name}", lambda _record, **_kwargs: {})
    payload = AgentUpdate(invoicing=invoicing) if record_name == "agent" else AffiliateUpdate(invoicing=invoicing)
    update(_DbCommitStub(), record.id, payload, SimpleNamespace(id=record.user_id))
    assert record.invoicing.country_id == 64


def test_agent_profile_save_allows_unchanged_locked_bank_details(monkeypatch):
    """A complete self-service form must not fail just by echoing saved bank fields."""
    record = SimpleNamespace(
        id=7,
        user_id=41,
        invoicing=SimpleNamespace(
            preferred_payment_method="bank_transfer", account_name="Test", account_number="1234",
            bank_name="Bank", bank_branch="Branch", swift_code="SWIFT", iban="",
            country_id=1,
        ),
        contacts=[], business_info=None,
    )
    monkeypatch.setattr("app.services.agents.get_agent", lambda _db, _id: record)
    monkeypatch.setattr("app.services.agents.serialize_agent", lambda _record, **_kwargs: {})
    payload = AgentUpdate(invoicing=AgentInvoicingUpdate(
        preferred_payment_method="bank_transfer", account_name="Test", account_number="1234",
        bank_name="Bank", bank_branch="Branch", swift_code="SWIFT", iban="",
        country_id=64,
    ))

    update_agent(_DbCommitStub(), record.id, payload, SimpleNamespace(id=record.user_id))

    assert record.invoicing.account_number == "1234"
    assert record.invoicing.country_id == 64


def test_supplier_cannot_lower_an_agreed_commission_rate(monkeypatch):
    """The self-service UI's increase-only rule must hold for direct API use."""
    supplier = SimpleNamespace(id=7, user_id=41, commission_percentage=15)
    monkeypatch.setattr("app.services.suppliers.get_supplier", lambda _db, _supplier_id: supplier)
    monkeypatch.setattr("app.services.suppliers.serialize_supplier", lambda _supplier: {})
    monkeypatch.setattr("app.services.settings.get_commission_percentage", lambda _db: 10)

    with pytest.raises(HTTPException) as exc:
        update_supplier(
            SimpleNamespace(),
            supplier.id,
            SupplierUpdate(commission_percentage=14),
            SimpleNamespace(id=supplier.user_id),
        )

    assert exc.value.status_code == 400
    assert "only be increased" in exc.value.detail


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


def test_booking_rejects_more_travellers_than_the_tour_group_limit():
    tour = SimpleNamespace(id=9, status="published", max_group_size=6)

    class TourQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return tour

    class Db:
        def query(self, _model):
            return TourQuery()

    data = BookingCreate(
        tour_id=tour.id,
        customer_id=1,
        booking_source="admin",
        no_of_adults=7,
        no_of_children=0,
        no_of_infants=0,
    )

    with pytest.raises(HTTPException) as exc:
        _price_booking(Db(), data)

    assert exc.value.status_code == 400
    assert "maximum of 6 travellers" in exc.value.detail


def test_calendar_remaining_capacity_decreases_from_the_group_limit_after_a_booking():
    tour = SimpleNamespace(max_group_size=6)
    calendar = SimpleNamespace(available_seats=10, booked_seats=1)
    assert _bookable_calendar_capacity(tour, calendar) - calendar.booked_seats == 5


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


def test_gateway_rejects_partial_payment_without_a_configured_deposit():
    # No tour attached (or a tour with no deposit configured) means the
    # booking has no supplier-defined deposit floor, so any amount below
    # the full outstanding balance must be rejected rather than accepted
    # as an arbitrary partial payment.
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, payment_booking(), "300.00", customer_user())
    assert exc.value.status_code == 400


def test_gateway_accepts_a_deposit_at_or_above_the_configured_minimum():
    tour = SimpleNamespace(deposit_type="fixed", booking_deposit=200, deposit_cutoff_days=None)
    row = payment_booking(tour=tour)
    amount = _validate_payment_request(None, row, "300.00", customer_user())
    assert str(amount) == "300.00"


def test_gateway_rejects_a_deposit_below_the_configured_minimum():
    tour = SimpleNamespace(deposit_type="fixed", booking_deposit=200, deposit_cutoff_days=None)
    row = payment_booking(tour=tour)
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, row, "100.00", customer_user())
    assert exc.value.status_code == 400


def test_gateway_rejects_overpayment():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, payment_booking(), "1000.01", customer_user())
    assert exc.value.status_code == 400


def test_gateway_requires_the_immutable_booking_currency():
    assert _validate_payment_currency(payment_booking(), "usd") == "USD"
    with pytest.raises(HTTPException) as exc:
        _validate_payment_currency(payment_booking(), "INR")
    assert exc.value.status_code == 400


def test_gateway_rejects_payment_from_another_customer():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, payment_booking(), "300.00", customer_user(99))
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
        _validate_payment_request(None, payment_booking(booking_status="cancelled"), "300.00", customer_user())
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


def test_supplier_assignment_email_requires_a_settled_booking_total():
    assert _is_booking_fully_paid(SimpleNamespace(payment_status="paid", final_amount=100, total_cost=100, amount_paid=100)) is True
    assert _is_booking_fully_paid(SimpleNamespace(payment_status="paid", final_amount=100, total_cost=100, amount_paid=0)) is False
    assert _is_booking_fully_paid(SimpleNamespace(payment_status="partially_paid", final_amount=100, total_cost=100, amount_paid=100)) is False


def test_customer_cannot_attach_an_agent_to_a_booking():
    """A traveller email/customer_id cannot create an Agent portal link."""
    data = BookingCreate(customer_id=1, agent_id=7, booking_source="customer", no_of_adults=1)
    actor = SimpleNamespace(id=42, role=SimpleNamespace(slug="customer"), user_roles=[])

    with pytest.raises(HTTPException) as exc:
        create_booking(SimpleNamespace(), data, actor=actor)

    assert exc.value.status_code == 403
    assert "cannot create or attach agent bookings" in exc.value.detail


def test_agent_self_update_rejects_admin_only_fields():
    with pytest.raises(ValidationError):
        AgentSelfUpdate(agent_name="Safe Agency", status="active")


def test_agent_role_detection_handles_agent_reseller():
    actor = SimpleNamespace(role=SimpleNamespace(slug="agent-reseller"))
    assert is_agent_user(actor) is True
