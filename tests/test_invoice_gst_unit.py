from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.invoices import InvoiceEmailRequest, InvoiceGenerateRequest
from app.schemas.bookings import BookingCommunicationCreate, MessageReplyCreate
from app.services import invoices


def test_gst_is_split_from_charged_total_without_increasing_invoice_total():
    subtotal, gst = invoices.split_gst_inclusive(Decimal("1180.00"), Decimal("0.18"))

    assert subtotal == Decimal("1000.00")
    assert gst == Decimal("180.00")
    assert subtotal + gst == Decimal("1180.00")


def test_gst_split_rounds_money_and_preserves_total():
    subtotal, gst = invoices.split_gst_inclusive(Decimal("1000.00"), Decimal("0.18"))

    assert subtotal == Decimal("847.46")
    assert gst == Decimal("152.54")
    assert subtotal + gst == Decimal("1000.00")


def test_zero_gst_keeps_the_full_amount_as_subtotal():
    assert invoices.split_gst_inclusive("500.00", 0) == (
        Decimal("500.00"),
        Decimal("0.00"),
    )


def test_invoice_schema_rejects_gst_rate_above_one_hundred_percent():
    with pytest.raises(ValidationError):
        InvoiceGenerateRequest(booking_id=1, gst_rate=Decimal("1.01"))


def test_auto_invoice_type_reflects_outstanding_balance():
    assert invoices._invoice_type("auto", Decimal("1.00")) == "partial_payment"
    assert invoices._invoice_type("auto", Decimal("0.00")) == "full_payment"
    assert invoices._invoice_type("tax_invoice", Decimal("50.00")) == "tax_invoice"


def test_failed_smtp_does_not_mark_invoice_as_emailed(monkeypatch):
    invoice = SimpleNamespace(
        id=7,
        invoice_number="TVA-INV-000007",
        booking=SimpleNamespace(
            customer=SimpleNamespace(user=SimpleNamespace(email="customer@example.com"))
        ),
        currency="INR",
        total_amount=Decimal("1000.00"),
        amount_due=Decimal("700.00"),
        balance_due_date=None,
        pdf_path=None,
        status="generated",
        emailed_at=None,
    )
    monkeypatch.setattr(invoices, "get_invoice", lambda *_args, **_kwargs: invoice)
    monkeypatch.setattr("app.utils.mailer.try_send_email", lambda *_args, **_kwargs: False)

    with pytest.raises(HTTPException) as error:
        invoices.email_invoice_to_customer(
            SimpleNamespace(),
            invoice.id,
            InvoiceEmailRequest(),
            SimpleNamespace(id=1),
        )

    assert error.value.status_code == 502
    assert invoice.status == "generated"
    assert invoice.emailed_at is None


@pytest.mark.parametrize(
    "payload",
    [
        lambda: BookingCommunicationCreate(message="   "),
        lambda: BookingCommunicationCreate(message="Hello", visibility="unknown"),
        lambda: BookingCommunicationCreate(message="Hello", message_type="unknown"),
        lambda: MessageReplyCreate(message="   "),
    ],
)
def test_message_threads_reject_empty_or_unsupported_content(payload):
    with pytest.raises(ValidationError):
        payload()
