from decimal import Decimal
from types import SimpleNamespace

from app.services import notification_delivery


def test_lifecycle_delivery_payload_serializes_decimal_template_values(monkeypatch):
    """A payment notification must not fail while being queued for email."""
    row = SimpleNamespace(id=123, payload_json=None)
    scheduled = []

    monkeypatch.setattr(notification_delivery, "reserve_delivery", lambda *_args, **_kwargs: row)
    from app.utils import mailer
    monkeypatch.setattr(mailer, "dispatch_email_task", lambda *_args: scheduled.append(True))

    queued = notification_delivery.dispatch_lifecycle_email(
        SimpleNamespace(), event="payment_received", entity_type="booking", entity_id=43,
        recipient_type="customer", recipient_email="customer@example.test",
        template_key="booking_payment_received",
        values={"amount": Decimal("252.91"), "nested": {"tax": Decimal("0.00")}},
        fallback_subject="Payment received", fallback_html="<p>Payment received</p>",
    )

    assert queued is True
    assert row.payload_json["values"] == {"amount": "252.91", "nested": {"tax": "0.00"}}
    assert scheduled == [True]
