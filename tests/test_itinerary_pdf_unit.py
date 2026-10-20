from pathlib import Path

from app.utils import itinerary_pdf
from app.utils import invoices_pdf


def test_fallback_is_a_valid_pdf_when_reportlab_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(itinerary_pdf, "REPORTLAB_AVAILABLE", False)
    output = Path(tmp_path) / "itinerary.pdf"

    itinerary_pdf.generate_pdf(output, {
        "booking_code": "TVAC-1",
        "tour_name": "Australia Highlights",
        "customer_name": "Traveller",
        "tour_date": "2026-11-14",
        "days": [{"day": 1, "title": "Sydney", "location": "Sydney", "description": "Arrival", "meals": "Dinner", "transport": "Coach"}],
    })

    content = output.read_bytes()
    assert content.startswith(b"%PDF-")
    assert b"xref" in content and content.rstrip().endswith(b"%%EOF")


def test_invoice_fallback_is_a_valid_pdf_when_reportlab_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(invoices_pdf, "REPORTLAB_AVAILABLE", False)
    output = Path(tmp_path) / "invoice.pdf"

    invoices_pdf.generate_pdf(output, {
        "invoice_number": "INV-1", "booking_code": "TVAC-1", "customer_name": "Traveller",
        "tour_name": "Australia Highlights", "traveller_names": "Traveller", "payment_method": "Card",
        "invoice_date": "2026-10-20", "status": "paid", "currency": "AUD",
        "subtotal_amount": "4.50", "gst_amount": "0", "total_amount": "4.50",
        "amount_paid": "4.50", "amount_due": "0", "items": [],
    })

    content = output.read_bytes()
    assert content.startswith(b"%PDF-")
    assert b"xref" in content and content.rstrip().endswith(b"%%EOF")
