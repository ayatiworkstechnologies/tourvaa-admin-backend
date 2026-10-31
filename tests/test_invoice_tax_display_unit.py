from decimal import Decimal
from types import SimpleNamespace

from app.services.invoices import _document_line_items


def test_included_tax_has_no_disclosed_amount_or_rate():
    booking = SimpleNamespace(
        adults_count=2,
        no_of_adults=0,
        children_count=1,
        no_of_children=0,
        base_amount=Decimal("1450.00"),
        optional_activity_amount=Decimal("180.00"),
        accommodation_amount=Decimal("0"),
        extension_amount=Decimal("0"),
        discount_amount=Decimal("65.00"),
        group_discount_amount=Decimal("0"),
        tax_amount=Decimal("156.50"),
        booking_code="TEST",
        id=1,
        tour_name="Test tour",
    )

    rows = _document_line_items(booking, Decimal("1565.00"), Decimal("1408.50"), Decimal("156.50"))
    tax_row = next(row for row in rows if row["description"] == "Including Tax")

    assert tax_row["quantity"] == "Included"
    assert tax_row["unit_price"] == ""
    assert tax_row["total_price"] == ""
