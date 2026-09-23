"""Unit tests for the commission-deduction money split and the booking
financial snapshot (no server or database needed)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.bookings import (
    _recompute_tourvaa_net_revenue,
    affiliate_eligible_amount,
    compute_agent_commission,
    compute_booking_financial_split,
    compute_booking_supplier_financials,
    remaining_channel_commission_pool,
)

D = Decimal


def test_direct_booking_split_120_at_10_percent():
    r = compute_booking_financial_split(base_amount=120, commission_percentage=10)
    assert r["commission_base_amount"] == D("120.00")
    assert r["commission_amount"] == D("12.00")
    assert r["supplier_net_payable"] == D("108.00")
    assert r["tourvaa_gross_revenue"] == D("12.00")


def test_agent_commission_is_carved_out_of_tourvaa_share():
    split = compute_booking_financial_split(base_amount=120, commission_percentage=10)
    agent = SimpleNamespace(discount_type="percentage", discount_value=D("3"))
    agent_amount = compute_agent_commission(agent, split["commission_base_amount"])
    assert agent_amount == D("3.60")
    booking = SimpleNamespace(tourvaa_gross_revenue=split["tourvaa_gross_revenue"], tourvaa_commission_amount=split["commission_amount"],
                              agent_commission_amount=agent_amount, affiliate_commission_amount=None, tourvaa_net_revenue=None)
    _recompute_tourvaa_net_revenue(booking)
    assert booking.tourvaa_net_revenue == D("8.40")


def test_tax_and_fees_are_not_inputs_to_the_supplier_split():
    # Customer pays 120 + tax 6 + service 5 + gateway 2 = 133; the split only
    # ever sees the 120 tour amount, so supplier stays at 108.
    r = compute_booking_financial_split(base_amount=120, commission_percentage=10)
    assert r["supplier_net_payable"] == D("108.00")
    assert r["commission_amount"] == D("12.00")


def test_tourvaa_funded_promo_keeps_supplier_whole():
    r = compute_booking_financial_split(base_amount=120, promo_discount_amount=5, promo_discount_funded_by="TOURVAA", commission_percentage=10)
    assert r["supplier_net_payable"] == D("108.00")
    assert r["tourvaa_discount_share_amount"] == D("5.00")
    assert r["tourvaa_gross_revenue"] == D("7.00")


def test_supplier_funded_promo_reduces_supplier_payout():
    r = compute_booking_financial_split(base_amount=120, promo_discount_amount=5, promo_discount_funded_by="SUPPLIER", commission_percentage=10)
    assert r["commission_base_amount"] == D("115.00")
    assert r["supplier_net_payable"] == D("103.50")


def test_shared_discount_splits_50_50():
    r = compute_booking_financial_split(base_amount=120, promo_discount_amount=10, promo_discount_funded_by="SHARED", commission_percentage=10)
    assert r["supplier_discount_share_amount"] == D("5.00")
    assert r["tourvaa_discount_share_amount"] == D("5.00")


def test_group_discount_is_deducted_once_not_twice():
    # Adults+children 500, infant 50 -> base 550; 10% group tier on the 500
    # = 50. Supplier-funded: commission base 500, not 550 - 50 - 45.45.
    r = compute_booking_financial_split(base_amount=550, group_discount_amount=50, commission_percentage=10)
    assert r["commission_base_amount"] == D("500.00")
    assert r["supplier_net_payable"] == D("450.00")


def test_tourvaa_funded_group_discount_is_absorbed_by_tourvaa():
    r = compute_booking_financial_split(base_amount=550, group_discount_amount=50, group_discount_funded_by="TOURVAA", commission_percentage=10)
    assert r["commission_base_amount"] == D("550.00")
    assert r["supplier_net_payable"] == D("495.00")
    assert r["tourvaa_gross_revenue"] == D("5.00")


def test_non_commissionable_and_cost_plus_addons():
    r = compute_booking_financial_split(
        base_amount=100, addon_total=70, non_commissionable_addon_amount=20,
        cost_plus_customer_amount=30, cost_plus_supplier_payable=18, commission_percentage=10,
    )
    # Commission base = 100 + (70 - 20 - 30) = 120 -> commission 12.
    assert r["commission_base_amount"] == D("120.00")
    assert r["commission_amount"] == D("12.00")
    # Supplier: 120 - 12 + 20 (full non-commissionable) + 18 (cost) = 146.
    assert r["supplier_net_payable"] == D("146.00")
    # Tourvaa: 12 commission + 12 cost-plus margin.
    assert r["tourvaa_gross_revenue"] == D("24.00")


@pytest.mark.parametrize("funded_by", ["SUPPLIER", "TOURVAA", "SHARED"])
def test_supplier_plus_tourvaa_equals_customer_amount_before_tax_and_fees(funded_by):
    base, group, promo, addons = D("550"), D("50"), D("20"), D("70")
    r = compute_booking_financial_split(
        base_amount=base, group_discount_amount=group, group_discount_funded_by=funded_by,
        promo_discount_amount=promo, promo_discount_funded_by=funded_by, addon_total=addons,
        non_commissionable_addon_amount=10, cost_plus_customer_amount=15, cost_plus_supplier_payable=9,
        commission_percentage=D("12.5"),
    )
    assert r["supplier_net_payable"] + r["tourvaa_gross_revenue"] == base - group - promo + addons


def test_agent_and_affiliate_on_same_booking_both_deducted():
    booking = SimpleNamespace(tourvaa_gross_revenue=D("12.00"), tourvaa_commission_amount=D("12.00"),
                              agent_commission_amount=D("3.60"), affiliate_commission_amount=None, tourvaa_net_revenue=None)
    assert remaining_channel_commission_pool(booking) == D("8.40")
    booking.affiliate_commission_amount = D("3.60")
    _recompute_tourvaa_net_revenue(booking)
    assert booking.tourvaa_net_revenue == D("4.80")


def _locked_booking(**overrides):
    values = dict(
        supplier_id=1, currency="USD", customer_selling_price=D("133"), final_amount=D("133"), total_cost=D("133"),
        financials_locked_at="2026-09-23", supplier_net_payable=D("108.00"), supplier_gross_amount=D("120.00"),
        commission_base_amount=D("120.00"), tourvaa_commission_percentage=D("10"), tourvaa_commission_amount=D("12.00"),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_supplier_financials_read_the_locked_snapshot_without_db():
    # db=None: a locked booking must never query today's slab/commission.
    r = compute_booking_supplier_financials(None, _locked_booking())
    assert r["net_payable"] == D("108.00")
    assert r["commission_amount"] == D("12.00")
    assert r["gross_amount"] == D("120.00")


def test_affiliate_base_is_the_commission_base_not_the_customer_total():
    assert affiliate_eligible_amount(_locked_booking()) == D("120.00")
