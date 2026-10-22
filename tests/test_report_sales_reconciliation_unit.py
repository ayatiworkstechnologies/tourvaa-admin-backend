from decimal import Decimal

from app.routers.reports import _sales_reconciliation


def test_monthly_gross_sales_reconciles_settled_and_outstanding_amounts():
    result = _sales_reconciliation("258368.56", "0.00", "258368.56")

    assert result["gross_sales"] == Decimal("258368.56")
    assert result["settled_amount"] + result["outstanding_amount"] == result["gross_sales"]
    assert result["reconciliation_difference"] == Decimal("0.00")


def test_reconciliation_exposes_inconsistent_legacy_booking_amounts():
    result = _sales_reconciliation("100.00", "40.00", "50.00")

    assert result["reconciliation_difference"] == Decimal("10.00")
