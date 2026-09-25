import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routers import affiliate_payouts, payments
from app.schemas.tours import PricingPayload
from app.services.tours import _apply_pricing_computation, _ser_pricing


def test_payment_money_actions_do_not_accept_legacy_edit_permission():
    for endpoint in (payments.capture, payments.void, payments.refund_payment):
        source = inspect.getsource(endpoint)
        assert "update-payments" not in source


def test_affiliate_mark_paid_requires_dedicated_permission():
    source = inspect.getsource(affiliate_payouts.mark_paid)
    assert 'require_any_permission("affiliate_payouts.mark_paid")' in source
    assert '"affiliate_payouts.process",' not in source


def test_admin_markup_is_ignored_by_commission_only_pricing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(supplier=None)
    row = SimpleNamespace(
        id=1,
        tour_id=2,
        passenger_from=1,
        passenger_to=4,
        adult_price=200.0,
        child_price=100.0,
        commission_percentage=None,
        supplier_price=0.0,
        final_price=0.0,
        supplier_final_adult_price=0.0,
        supplier_final_child_price=0.0,
        admin_markup_type="percentage",
        admin_markup_value=25.0,
        storefront_adult_price=250.0,
        storefront_child_price=125.0,
        currency="USD",
        status="active",
        created_at=None,
        updated_at=None,
    )
    payload = PricingPayload(
        passenger_from=1,
        passenger_to=4,
        adult_price=200,
        child_price=100,
        commission_percentage=10,
        admin_markup_value=50,
    )
    actor = SimpleNamespace(role=SimpleNamespace(slug="admin"))

    with (
        patch("app.services.bookings.resolve_effective_commission_percentage", return_value=10),
        patch("app.services.supplier_scope.is_supplier_user", return_value=False),
    ):
        _apply_pricing_computation(db, 2, row, payload, actor)

    assert row.admin_markup_value == 0
    assert row.storefront_adult_price == 200
    assert row.storefront_child_price == 100
    assert row.supplier_final_adult_price == 180
    assert _ser_pricing(row)["admin_markup_value"] == 0
