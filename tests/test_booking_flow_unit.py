from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.bookings import (
    _apply_customer_checkout_currency,
    _bookable_calendar_capacity,
    _booking_status_label,
    _booking_email_recipient,
    _booking_payment_email_summary,
    _booking_seat_count,
    _ensure_booking_access,
    _hide_agent_reservation_payment_from_supplier,
    _hide_supplier_reassignment_from_external_partner,
    _is_day_tour,
    _is_booking_fully_paid,
    _price_booking,
    _start_supplier_decision,
    _validate_booking_status_transition,
    _validate_customer_travellers,
    _validate_supplier_lifecycle_transition,
    create_booking,
    notify_booking_received_after_payment,
    supplier_amount_in_booking_currency,
    _has_secured_booking_funds,
)
from app.services.payments import FINAL_BOOKING_CONFIRMATION_STATUSES, _derive_booking_status, _ensure_payment_access, _status_after_payment_sync
from app.services.discounts import find_active_discount_stack
from app.routers.payments_gateway import _ensure_booking_payment_access, _minimum_deposit_amount, _require_captured_amount_matches_pending, _validate_payment_currency, _validate_payment_request, _validate_paypal_payment_currency, _validate_stripe_minimum_charge
from app.schemas.bookings import BookingCreate, BookingTravellerPayload
from app.schemas.checkout import CheckoutConfirm
from app.schemas.tours import AccommodationExtraPayload
from app.schemas.agents import AgentSelfUpdate
from app.schemas.agents import AgentInvoicingUpdate, AgentUpdate
from app.schemas.affiliates import AffiliateInvoicingUpdate, AffiliateUpdate
from app.schemas.suppliers import SupplierInvoicingUpdate, SupplierSelfUpdate, SupplierUpdate
from app.services.agent_scope import is_agent_user
from app.services.supplier_scope import is_supplier_user, reject_supplier_review_action
from app.services.suppliers import _mask_bank_identifier, update_supplier
from app.services.agents import _mask_bank_identifier as mask_agent_bank_identifier, update_agent
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


def test_gateway_authorization_capture_waits_for_final_booking_confirmation():
    assert FINAL_BOOKING_CONFIRMATION_STATUSES == {"confirmed", "ready_to_travel", "ongoing", "completed"}
    assert "supplier_accepted" not in FINAL_BOOKING_CONFIRMATION_STATUSES


def test_gateway_rejects_charge_below_stripe_settlement_minimum(monkeypatch):
    from app.routers import payments_gateway

    monkeypatch.setattr(
        payments_gateway,
        "convert_amount",
        lambda amount, source, target: (Decimal("0.30") if source == "INR" else Decimal("26.00"), Decimal("1"), {}),
    )

    with pytest.raises(HTTPException) as error:
        _validate_stripe_minimum_charge(Decimal("16.00"), "INR")

    assert error.value.status_code == 422
    assert "at least INR 26.00" in error.value.detail


def test_gateway_rejects_paypal_unsupported_booking_currency_before_request():
    with pytest.raises(HTTPException) as error:
        _validate_paypal_payment_currency("INR")

    assert error.value.status_code == 422
    assert "PayPal is not available for INR" in error.value.detail


def test_automatic_discount_uses_booking_date_not_future_departure_date():
    now = datetime.now(timezone.utc)
    discount = SimpleNamespace(
        id=1,
        status="active",
        discount_code=None,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        usage_limit=None,
        used_count=0,
        discount_type="percentage",
        discount_value=20,
        tour_id=7,
        funded_by="TOURVAA",
    )

    class Query:
        def filter(self, *_conditions):
            return self

        def with_for_update(self):
            return self

        def all(self):
            return [discount]

        def first(self):
            return None

    class Session:
        def query(self, *_entities):
            return Query()

    tour = SimpleNamespace(id=7, category_id=None, country_id=None, price_start_per_person=100)
    stack = find_active_discount_stack(Session(), tour, effective_at=now + timedelta(days=730))

    assert stack["tourvaa"] is discount


@pytest.mark.parametrize(
    "status",
    ["pending_supplier_assignment", "payment_authorized", "pending_supplier_acceptance", "supplier_accepted"],
)
def test_customer_and_agent_confirmation_pending_labels_match_the_status_standard(status):
    expected = "Booking Request Received"

    assert _booking_status_label(status, "customer") == expected
    assert _booking_status_label(status, "agent") == expected


def test_supplier_view_masks_agent_reservation_payment_and_enables_decision_state():
    row = booking(
        booking_source="agent",
        payment_status="credit_approval_pending",
        agent_payment_method="credit",
    )
    data = {
        "booking_status": "pending_credit_approval",
        "payment_status": "credit_approval_pending",
        "payment_type": "full",
        "agent_payment_method": "credit",
        "agent_reference": "PRIVATE-REF",
        "status_history": [
            {"old_status": None, "new_status": "pending_credit_approval"},
        ],
    }

    result = _hide_agent_reservation_payment_from_supplier(data, row)

    assert result["booking_status"] == "pending_supplier_acceptance"
    assert result["payment_status"] is None
    assert result["payment_type"] is None
    assert result["agent_payment_method"] is None
    assert result["agent_reference"] is None
    assert result["status_history"] == []


def test_supplier_view_masks_pay_later_agent_reservation_too():
    row = booking(
        booking_source="agent",
        payment_status="pending",
        agent_payment_method="pay_later",
        supplier_acceptance_status="pending",
    )
    data = {
        "booking_status": "pending_supplier_acceptance",
        "payment_status": "pending",
        "payment_type": "full",
        "agent_payment_method": "pay_later",
        "agent_reference": "PRIVATE-REF",
        "status_history": [],
    }

    result = _hide_agent_reservation_payment_from_supplier(data, row)

    assert result["booking_status"] == "pending_supplier_acceptance"
    assert result["payment_status"] is None
    assert result["agent_payment_method"] is None


@pytest.mark.parametrize("role", ["customer", "agent"])
def test_supplier_decline_reassignment_is_neutral_and_reason_free_for_external_partners(role):
    row = booking(
        booking_status="supplier_reassignment_required",
        supplier_acceptance_status="declined",
        cancellation_source="supplier_reassignment",
    )
    data = {
        "booking_status": "supplier_reassignment_required",
        "supplier_acceptance_status": "declined",
        "cancellation_reason": "No vehicle available",
        "cancellation_source": "supplier_reassignment",
        "cancelled_at": "2026-10-08T00:00:00Z",
        "status_history": [
            {"change_source": "supplier_reassignment", "new_status": "supplier_reassignment_required"},
            {"change_source": "admin", "new_status": "pending_supplier_acceptance"},
        ],
    }

    result = _hide_supplier_reassignment_from_external_partner(data, row, role)

    assert result["booking_status"] == "pending_supplier_acceptance"
    assert result["supplier_acceptance_status"] == "pending"
    assert result["cancellation_reason"] is None
    assert result["status_history"] == [{"change_source": "admin", "new_status": "pending_supplier_acceptance"}]


def test_supplier_self_update_rejects_admin_managed_fields():
    with pytest.raises(ValidationError):
        SupplierSelfUpdate(status="active")


def test_supplier_bank_country_and_masked_identifiers_are_supported():
    """Suppliers retain a distinct bank country but never receive full saved IDs."""
    payload = SupplierInvoicingUpdate(bank_country_id=64, account_number="1234567890122323")
    assert payload.bank_country_id == 64
    assert _mask_bank_identifier(payload.account_number) == "************2323"
    assert _mask_bank_identifier("123") == "123"


def test_agent_bank_identifiers_only_expose_the_last_four_characters():
    """The agent portal must not receive complete locked payout identifiers."""
    assert mask_agent_bank_identifier("1234567890122323") == "************2323"
    assert mask_agent_bank_identifier("ABCDEFGH1234") == "********1234"


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


def test_paid_booking_with_supplier_acceptance_awaits_tourvaa_confirmation():
    row = booking(supplier_acceptance_status="accepted")
    assert _status_after_payment_sync(row, "paid") == "supplier_accepted"


def test_paid_unassigned_booking_awaits_supplier_assignment():
    row = booking(supplier_id=None, supplier_acceptance_status="not_assigned")
    assert _status_after_payment_sync(row, "paid") == "pending_supplier_assignment"


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


def test_accommodation_addons_use_category_specific_price_types():
    saved = AccommodationExtraPayload(
        accommodation_name="Deluxe room",
        category="room_upgrade",
        price_type="per_person",
    )
    assert saved.price_type == "per_person"

    additional_night = AccommodationExtraPayload(
        accommodation_name="Extra night",
        category="additional_night",
        price_type="per_room",
    )
    assert additional_night.price_type == "per_room"

    with pytest.raises(ValidationError):
        AccommodationExtraPayload(accommodation_name="Per-room suite", category="room_upgrade", price_type="per_room")
    with pytest.raises(ValidationError):
        AccommodationExtraPayload(accommodation_name="Airport pickup", category="pickup", price_type="per_person")


def test_day_tours_without_an_overnight_stay_are_treated_as_day_tours():
    assert _is_day_tour(SimpleNamespace(number_of_nights=0)) is True
    assert _is_day_tour(SimpleNamespace(number_of_nights=2)) is False
    assert _is_day_tour(SimpleNamespace(number_of_nights=None, number_of_days=1)) is True
    assert _is_day_tour(SimpleNamespace(number_of_nights=None, number_of_days=2)) is False
    assert _is_day_tour(None) is False


def test_booking_capacity_is_not_limited_by_the_vehicle_group_size():
    """A 6-seat vehicle grouping must not prevent a 20-seat departure
    booking; operations can allocate multiple vehicles."""
    tour = SimpleNamespace(max_group_size=6)
    calendar = SimpleNamespace(available_seats=20, booked_seats=0)

    assert _bookable_calendar_capacity(tour, calendar) == 20


def test_calendar_remaining_capacity_uses_departure_capacity_not_booking_group_limit():
    tour = SimpleNamespace(max_group_size=6)
    calendar = SimpleNamespace(available_seats=20, booked_seats=4)
    assert _bookable_calendar_capacity(tour, calendar) - calendar.booked_seats == 16


def payment_booking(**overrides):
    values = {
        "booking_status": "pending_payment",
        "amount_pending": "1000.00",
        "currency": "USD",
        "payment_type": "partial",
        "customer": SimpleNamespace(user_id=42),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def customer_user(user_id=42):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(slug="customer"))


def agent_user(user_id=73):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(slug="agent-reseller"))


def test_gateway_rejects_partial_payment_without_a_configured_deposit():
    # No tour attached (or a tour with no deposit configured) means the
    # booking has no supplier-defined deposit floor, so any amount below
    # the full outstanding balance must be rejected rather than accepted
    # as an arbitrary partial payment.
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, payment_booking(), "300.00", customer_user())
    assert exc.value.status_code == 400


def test_checkout_confirmation_accepts_only_supported_customer_payment_choices():
    assert CheckoutConfirm(payment_type="partial").payment_type == "partial"
    assert CheckoutConfirm(payment_type="full").payment_type == "full"
    with pytest.raises(ValidationError):
        CheckoutConfirm(payment_type="deposit")


def test_gateway_accepts_a_deposit_at_or_above_the_configured_minimum():
    tour = SimpleNamespace(deposit_type="fixed", booking_deposit=200, deposit_cutoff_days=None)
    row = payment_booking(tour=tour)
    amount = _validate_payment_request(None, row, "300.00", customer_user())
    assert str(amount) == "300.00"


def test_gateway_rejects_deposit_for_a_booking_created_for_full_payment():
    """A current tour deposit rule cannot alter a historical full booking."""
    tour = SimpleNamespace(deposit_type="percentage", deposit_percentage=30, deposit_cutoff_days=None)
    row = payment_booking(tour=tour, payment_type="full")

    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, row, "300.00", customer_user())

    assert exc.value.status_code == 400
    assert "created for full payment" in exc.value.detail


def test_gateway_rejects_a_deposit_below_the_configured_minimum():
    tour = SimpleNamespace(deposit_type="fixed", booking_deposit=200, deposit_cutoff_days=None)
    row = payment_booking(tour=tour)
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, row, "100.00", customer_user())
    assert exc.value.status_code == 400


def test_gateway_requires_agent_bookings_to_pay_the_full_outstanding_balance():
    row = payment_booking(
        booking_source="agent",
        agent=SimpleNamespace(user_id=73),
        tour=SimpleNamespace(deposit_type="percentage", deposit_percentage=30, deposit_cutoff_days=None),
    )
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, row, "300.00", agent_user())
    assert exc.value.status_code == 400
    assert "paid in full" in exc.value.detail


def test_gateway_rejects_overpayment():
    with pytest.raises(HTTPException) as exc:
        _validate_payment_request(None, payment_booking(), "1000.01", customer_user())
    assert exc.value.status_code == 400


def test_gateway_requires_the_immutable_booking_currency():
    assert _validate_payment_currency(payment_booking(), "usd") == "USD"
    with pytest.raises(HTTPException) as exc:
        _validate_payment_currency(payment_booking(), "INR")
    assert exc.value.status_code == 400


def test_gateway_capture_must_match_the_selected_deposit_amount():
    """A deposit checkout must never settle the booking's full balance."""
    pending_payment = SimpleNamespace(id=41, total_amount="268.50")

    assert str(_require_captured_amount_matches_pending(pending_payment, "268.50", "Stripe")) == "268.50"
    with pytest.raises(HTTPException) as exc:
        _require_captured_amount_matches_pending(pending_payment, "895.00", "Stripe")
    assert exc.value.status_code == 409


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


def test_customer_cannot_read_an_agent_booking_payment():
    payment = SimpleNamespace(
        customer=SimpleNamespace(user_id=42),
        booking=SimpleNamespace(booking_source="agent"),
    )
    with pytest.raises(HTTPException) as exc:
        _ensure_payment_access(payment, customer_user())
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


def test_supplier_assignment_accepts_authorized_or_partially_paid_funds():
    assert _has_secured_booking_funds(SimpleNamespace(payment_status="authorized")) is True
    assert _has_secured_booking_funds(SimpleNamespace(payment_status="partially_paid")) is True
    assert _has_secured_booking_funds(SimpleNamespace(payment_status="paid")) is True
    assert _has_secured_booking_funds(SimpleNamespace(payment_status="pending")) is False


def test_booking_received_email_requires_secured_funds(monkeypatch):
    from app.services import bookings as booking_service
    from app.services import notifications as notification_service
    from app.services import notification_delivery
    from app.utils import notification_triggers

    sent = []
    monkeypatch.setattr(booking_service, "_send_booking_email", lambda *args, **kwargs: sent.append((args, kwargs)))
    monkeypatch.setattr(notification_service, "notify_admins", lambda *args, **kwargs: None)
    monkeypatch.setattr(notification_triggers, "email_admins", lambda *args, **kwargs: None)
    monkeypatch.setattr(notification_delivery, "dispatch_admin_lifecycle_emails", lambda *args, **kwargs: 0)
    paid_booking = SimpleNamespace(
        id=101, payment_status="partially_paid", final_amount=100, total_cost=100, amount_paid=25,
        customer=SimpleNamespace(full_name="Paid Customer", email="paid@example.test", user_id=None),
        booking_code="TV-101", tour_name="Paid Tour", tour_date="2027-06-01",
        adults_count=2, currency="USD", agent=None, supplier=None,
    )
    unpaid_booking = SimpleNamespace(
        id=102, payment_status="pending", final_amount=100, total_cost=100, amount_paid=0,
        customer=SimpleNamespace(full_name="Unpaid Customer", email="unpaid@example.test", user_id=None),
        agent=None, supplier=None,
    )
    authorized_booking = SimpleNamespace(
        id=103, payment_status="authorized", final_amount=100, total_cost=100, amount_paid=0,
        customer=SimpleNamespace(full_name="Authorized Customer", email="authorized@example.test", user_id=None),
        booking_code="TV-103", tour_name="Authorized Tour", tour_date="2027-06-02",
        adults_count=1, currency="INR", agent=None, supplier=None,
    )

    db = SimpleNamespace(commit=lambda: None)
    notify_booking_received_after_payment(db, unpaid_booking)
    notify_booking_received_after_payment(db, paid_booking)
    notify_booking_received_after_payment(db, authorized_booking)

    assert len(sent) == 2
    assert sent[0][0][1] == "booking_confirmation"
    assert sent[0][0][-1] == "paid@example.test"
    assert sent[1][0][1] == "booking_confirmation"
    assert sent[1][0][-1] == "authorized@example.test"


def test_booking_payment_email_summary_distinguishes_deposit_authorization_and_full_payment():
    deposit = SimpleNamespace(
        currency="NZD", final_amount=Decimal("100"), total_cost=Decimal("100"),
        amount_paid=Decimal("25"), payment_status="partially_paid", payment_type="partial",
    )
    authorized = SimpleNamespace(
        currency="NZD", final_amount=Decimal("100"), total_cost=Decimal("100"),
        amount_paid=Decimal("0"), payment_status="authorized", payment_type="full",
    )
    paid = SimpleNamespace(
        currency="NZD", final_amount=Decimal("100"), total_cost=Decimal("100"),
        amount_paid=Decimal("100"), payment_status="paid", payment_type="full",
    )

    assert _booking_payment_email_summary(deposit) == "Deposit paid: NZD 25.00\nRemaining balance: NZD 75.00"
    assert "no payment has been captured" in _booking_payment_email_summary(authorized)
    assert _booking_payment_email_summary(paid) == "Payment received in full: NZD 100.00"


def test_booking_status_label_uses_cancellation_source_without_changing_legacy_calls():
    assert _booking_status_label("cancelled", "customer") == "Cancelled by Tourvaa"
    assert _booking_status_label("cancelled", "customer", "customer_request") == "Cancelled by Customer"
    assert _booking_status_label("cancelled", "agent", "customer_unpaid_removed") == "Cancelled by Customer"
    assert _booking_status_label("cancelled", "customer", "supplier") == "Cancelled by Tourvaa"


def test_agent_booking_does_not_email_selected_customer_or_lead_traveller():
    booking_row = SimpleNamespace(
        booking_source="agent",
        customer=SimpleNamespace(full_name="Agency Customer", email="customer@example.test"),
        travellers=[
            SimpleNamespace(full_name="Other Traveller", first_name="Other", last_name="Traveller", email="other@example.test", is_primary_contact=False),
            SimpleNamespace(full_name="Lead Traveller", first_name="Lead", last_name="Traveller", email="lead@example.test", is_primary_contact=True),
        ],
    )

    assert _booking_email_recipient(booking_row) is None


def test_customer_cannot_access_an_agent_owned_booking():
    booking = SimpleNamespace(
        booking_source="agent",
        customer=SimpleNamespace(user_id=41),
        agent=SimpleNamespace(user_id=77),
        supplier=None,
    )
    customer = SimpleNamespace(id=41, role=SimpleNamespace(slug="customer"), user_roles=[])

    with pytest.raises(HTTPException) as exc:
        _ensure_booking_access(booking, customer)

    assert exc.value.status_code == 403


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


def test_customer_checkout_locks_selected_currency_without_converting_supplier_settlement(monkeypatch):
    from decimal import Decimal
    from app.services import currency as currency_service

    monkeypatch.setattr(
        currency_service,
        "convert_amount",
        lambda amount, source, target: (Decimal("95.00"), Decimal("95"), {"source": "unit_test_rates"}),
    )
    booking_row = SimpleNamespace(
        currency="CHF",
        display_currency="CHF",
        total_cost=Decimal("100"),
        base_amount=Decimal("80"),
        optional_activity_amount=Decimal("20"),
        accommodation_amount=Decimal("0"),
        extension_amount=Decimal("0"),
        non_commissionable_addon_amount=Decimal("0"),
        cost_plus_customer_amount=Decimal("0"),
        group_discount_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        surcharge_amount=Decimal("0"),
        service_fee_amount=Decimal("0"),
        gateway_fee_amount=Decimal("0"),
        final_amount=Decimal("100"),
        agent_net_price=Decimal("90"),
        agent_markup=Decimal("10"),
        customer_selling_price=Decimal("100"),
        amount_paid=Decimal("0"),
        amount_pending=Decimal("100"),
        supplier_base_amount=Decimal("70"),
        supplier_net_payable=Decimal("65"),
        commission_base_amount=Decimal("30"),
        tourvaa_commission_amount=Decimal("5"),
        agent_commission_amount=Decimal("3"),
    )
    addon = SimpleNamespace(unit_price=Decimal("10"), total_price=Decimal("20"))

    _apply_customer_checkout_currency(booking_row, "INR", "CHF", [addon])

    assert booking_row.currency == "INR"
    assert booking_row.display_currency == "INR"
    assert booking_row.exchange_rate == Decimal("95.000000")
    assert booking_row.exchange_rate_source == "unit_test_rates"
    assert booking_row.final_amount == Decimal("9500.00")
    assert booking_row.agent_net_price == Decimal("8550.00")
    assert booking_row.agent_markup == Decimal("950.00")
    assert booking_row.amount_pending == Decimal("9500.00")
    assert addon.unit_price == Decimal("950.00")
    assert addon.total_price == Decimal("1900.00")
    assert booking_row.supplier_net_payable == Decimal("65")
    assert booking_row.tourvaa_commission_amount == Decimal("5")
    assert booking_row.agent_commission_amount == Decimal("3")


def test_agent_booking_accepts_selected_display_currency():
    payload = BookingCreate(
        booking_source="agent",
        display_currency="INR",
        agreed_terms=True,
        agreed_cancellation_policy=True,
    )

    assert payload.display_currency == "INR"


def test_agent_commission_snapshot_uses_locked_rate_for_booking_currency():
    from decimal import Decimal

    booking_row = SimpleNamespace(
        supplier_currency="CHF",
        currency="INR",
        exchange_rate=Decimal("95"),
    )

    assert supplier_amount_in_booking_currency(booking_row, Decimal("3")) == Decimal("285.00")


def test_agent_ledger_keeps_supplier_currency_when_gateway_currency_differs():
    from decimal import Decimal
    from app.services.agent_ledger import create_ledger_entry

    class FakeDb:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

    booking_row = SimpleNamespace(
        id=7,
        supplier_currency="CHF",
        currency="INR",
    )
    db = FakeDb()

    entry = create_ledger_entry(
        db,
        booking=booking_row,
        agent_id=4,
        gross_amount=Decimal("100"),
        commission_amount=Decimal("3"),
        commission_percentage=Decimal("3"),
    )

    assert entry.currency == "CHF"
    assert entry.commission_amount == Decimal("3.00")
    assert db.added == [entry]


def test_fixed_supplier_deposit_is_converted_to_locked_booking_currency():
    from decimal import Decimal

    booking_row = SimpleNamespace(
        amount_pending=Decimal("9500"),
        amount_paid=Decimal("0"),
        booking_source="agent",
        supplier_currency="CHF",
        currency="INR",
        exchange_rate=Decimal("95"),
        tour_start_date=None,
        tour=SimpleNamespace(
            deposit_cutoff_days=None,
            deposit_type="fixed",
            deposit_percentage=None,
            booking_deposit=Decimal("10"),
        ),
    )

    assert _minimum_deposit_amount(None, booking_row) == Decimal("950.00")


def test_checkout_confirm_accepts_selected_display_currency():
    payload = CheckoutConfirm(display_currency="INR", agreed_terms=True, agreed_cancellation_policy=True)

    assert payload.display_currency == "INR"


def test_checkout_confirm_accepts_affiliate_ref_code():
    payload = CheckoutConfirm(
        affiliate_ref_code="AFF-TRACK-123",
        agreed_terms=True,
        agreed_cancellation_policy=True,
    )

    assert payload.affiliate_ref_code == "AFF-TRACK-123"


def test_checkout_confirm_rejects_malformed_display_currency():
    with pytest.raises(ValidationError):
        CheckoutConfirm(display_currency="rupees")
