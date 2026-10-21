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


def test_supplier_approval_reserves_a_durable_email_delivery(monkeypatch):
    """Supplier approval must not use the fire-and-forget SMTP helper."""
    from app.services import notification_delivery
    from app.utils import notification_triggers

    scheduled = {}
    in_app = []

    monkeypatch.setattr(notification_triggers, "notify_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "enqueue_notification", lambda *_args, **kwargs: in_app.append(kwargs))
    monkeypatch.setattr(notification_triggers, "_user_email", lambda *_args: "supplier@example.test")
    monkeypatch.setattr(notification_delivery, "dispatch_lifecycle_email", lambda *args, **kwargs: scheduled.update(args=args, kwargs=kwargs))

    db = SimpleNamespace(flush=lambda: None)
    background_tasks = object()
    notification_triggers.notify_supplier_approved(
        db,
        supplier_id=18,
        supplier_name="Example Supplier",
        user_id=27,
        background_tasks=background_tasks,
    )

    assert in_app and in_app[0]["user_id"] == 27
    assert scheduled["kwargs"]["event"] == "supplier_account_approved"
    assert scheduled["kwargs"]["entity_type"] == "supplier"
    assert scheduled["kwargs"]["entity_id"] == 18
    assert scheduled["kwargs"]["recipient_email"] == "supplier@example.test"
    assert scheduled["kwargs"]["background_tasks"] is background_tasks
