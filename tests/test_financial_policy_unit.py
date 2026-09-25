import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routers import affiliate_payouts, payments
from app.schemas.tours import PricingPayload
from app.services.discounts import find_best_discount_row
from app.services.tours import _apply_pricing_computation, _ser_pricing


def test_payment_money_actions_do_not_accept_legacy_edit_permission():
    for endpoint in (payments.capture, payments.void, payments.refund_payment):
        source = inspect.getsource(endpoint)
        assert "update-payments" not in source


def test_affiliate_mark_paid_requires_dedicated_permission():
    source = inspect.getsource(affiliate_payouts.mark_paid)
    assert 'require_any_permission("affiliate_payouts.mark_paid")' in source
    assert '"affiliate_payouts.process",' not in source


def _pricing_row():
    return SimpleNamespace(
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


def _apply(row, *, is_supplier: bool, markup_in_payload: float | None, is_update: bool = True, default_markup: float = 5, tour_markup: float | None = None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(supplier=None, admin_markup_percentage=tour_markup)
    payload = PricingPayload(
        passenger_from=1,
        passenger_to=4,
        adult_price=200,
        child_price=100,
        commission_percentage=10,
        admin_markup_value=markup_in_payload,
    )
    actor = SimpleNamespace(role=SimpleNamespace(slug="supplier" if is_supplier else "admin"))
    with (
        patch("app.services.bookings.resolve_effective_commission_percentage", return_value=10),
        patch("app.services.supplier_scope.is_supplier_user", return_value=is_supplier),
        patch("app.services.settings.get_default_admin_markup_percentage", return_value=default_markup),
    ):
        _apply_pricing_computation(db, 2, row, payload, actor, is_update=is_update)


def test_admin_sets_markup_and_storefront_price():
    row = _pricing_row()
    _apply(row, is_supplier=False, markup_in_payload=20)

    assert row.admin_markup_value == 20
    assert row.storefront_adult_price == 240   # 200 + 20%
    assert row.storefront_child_price == 120
    assert row.supplier_final_adult_price == 180  # commission still on the supplier price
    assert _ser_pricing(row)["admin_markup_value"] == 20


def test_supplier_cannot_change_markup():
    row = _pricing_row()  # existing admin-set markup of 25%
    _apply(row, is_supplier=True, markup_in_payload=0)

    assert row.admin_markup_value == 25
    assert row.storefront_adult_price == 250


def test_new_supplier_slab_follows_default_markup():
    row = _pricing_row()
    _apply(row, is_supplier=True, markup_in_payload=90, is_update=False, default_markup=5)

    assert row.admin_markup_value is None       # follows the platform default
    assert row.storefront_adult_price == 210    # 200 + default 5%


def test_slab_without_markup_uses_tour_markup_before_default():
    row = _pricing_row()
    _apply(row, is_supplier=False, markup_in_payload=None, default_markup=5, tour_markup=15)

    assert row.admin_markup_value is None
    assert row.storefront_adult_price == 230    # 200 + tour 15% (not the 5% default)


def test_admin_can_clear_markup_to_follow_default():
    row = _pricing_row()  # had its own 25%
    _apply(row, is_supplier=False, markup_in_payload=None, default_markup=10)

    assert row.admin_markup_value is None
    assert row.storefront_adult_price == 220    # 200 + default 10%
    assert _ser_pricing(row)["markup_follows_default"] is True


def test_automatic_discount_query_excludes_promo_codes():
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = []
    db = MagicMock()
    db.query.return_value = query
    tour = SimpleNamespace(id=7, category_id=None, country_id=None, price_start_per_person=100)

    assert find_best_discount_row(db, tour) is None
    expressions = " ".join(str(value) for value in query.filter.call_args.args)
    assert "tour_discounts.discount_code IS NULL" in expressions
