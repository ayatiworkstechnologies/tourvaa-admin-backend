"""The public price ladder (tour page "Group Rate Highlights" and cart) must
show the storefront price -- supplier price + Tourvaa markup -- never the
supplier's own adult_price/child_price. Guards against a regression where
the tour page showed 100/95/90 while admin and checkout used 105/99.75/94.50."""
from types import SimpleNamespace

from app.routers.public import _public_pricing_rows
from app.services.discounts import combined_discount_percent


def _slab(pax_from, pax_to, adult, child, store_adult, store_child):
    return SimpleNamespace(
        passenger_from=pax_from, passenger_to=pax_to, currency="USD",
        adult_price=adult, child_price=child,
        storefront_adult_price=store_adult, storefront_child_price=store_child,
    )


def test_multi_slab_ladder_uses_storefront_prices():
    rows = _public_pricing_rows([
        _slab(1, 1, 100, 80, 105, 84),
        _slab(2, 3, 95, 80, 99.75, 84),
        _slab(4, 6, 90, 75, 94.5, 78.75),
    ], [])
    assert [r["price_per_person"] for r in rows] == [105, 99.75, 94.5]
    assert [r["child_price_per_person"] for r in rows] == [84, 84, 78.75]


def test_single_slab_ladder_uses_storefront_price():
    rows = _public_pricing_rows([_slab(1, 10, 100, 80, 120, 96)], [])
    assert rows[0]["price_per_person"] == 120 and rows[0]["child_price_per_person"] == 96


def test_discount_applies_to_storefront_price():
    rows = _public_pricing_rows([_slab(1, 1, 100, 80, 105, 84), _slab(2, 3, 95, 80, 99.75, 84)], [], discount_percentage=10)
    assert rows[0]["original_price_per_person"] == 105 and rows[0]["price_per_person"] == 94.5


def test_supplier_discount_precedes_markup_and_tourvaa_discount():
    # Stored storefront 150 = raw supplier 100 + 50% markup. A 10%
    # supplier discount makes the publishable comparison price 135; Tourvaa's
    # subsequent 20% offer makes the final customer price 108. The legacy
    # comparison price remains 135, while the explicit price stages expose
    # the complete $150 -> $135 -> $108 customer calculation.
    rows = _public_pricing_rows(
        [_slab(1, 4, 100, 0, 150, 0)],
        [],
        {"supplier_discount_percentage": 10, "tourvaa_discount_percentage": 20},
    )
    assert rows[0]["original_price_per_person"] == 135
    assert rows[0]["storefront_original_price_per_person"] == 150
    assert rows[0]["supplier_discounted_price_per_person"] == 135
    assert rows[0]["price_per_person"] == 108


def test_supplier_only_discount_keeps_original_for_badge():
    rows = _public_pricing_rows(
        [_slab(1, 4, 100, 0, 150, 0)],
        [],
        {"supplier_discount_percentage": 10, "tourvaa_discount_percentage": None},
    )
    assert rows[0]["original_price_per_person"] == 150
    assert rows[0]["price_per_person"] == 135


def test_stacked_discount_badge_uses_the_effective_saving():
    assert combined_discount_percent(10, 15) == 23.5
