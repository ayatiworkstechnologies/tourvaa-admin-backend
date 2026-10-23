from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services import notification_delivery
from app.models.notifications import NotificationDelivery


def test_lifecycle_delivery_payload_serializes_decimal_template_values(monkeypatch):
    """A payment notification must not fail while being queued for email."""
    row = SimpleNamespace(id=123, payload_json=None)
    scheduled = []

    monkeypatch.setattr(notification_delivery, "reserve_delivery", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(notification_delivery, "_schedule_after_commit", lambda *_args: scheduled.append(True))

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


class _BackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, target, *args):
        self.tasks.append((target, args))


def test_delivery_worker_is_registered_only_after_outer_commit():
    db = Session(create_engine("sqlite://"))
    tasks = _BackgroundTasks()

    db.execute(text("select 1"))
    notification_delivery._schedule_after_commit(db, 41, tasks)
    assert tasks.tasks == []

    db.commit()
    assert tasks.tasks == [(notification_delivery._deliver_in_new_session, (41,))]


def test_delivery_worker_is_not_registered_after_rollback():
    db = Session(create_engine("sqlite://"))
    tasks = _BackgroundTasks()

    db.execute(text("select 1"))
    notification_delivery._schedule_after_commit(db, 42, tasks)
    db.rollback()
    db.execute(text("select 1"))
    db.commit()

    assert tasks.tasks == []


def test_delivery_worker_does_not_send_a_row_already_being_processed(monkeypatch):
    row = SimpleNamespace(status="processing", attempt_count=1)

    class Query:
        def filter(self, *_args):
            return self

        def with_for_update(self):
            return self

        def first(self):
            return row

        def update(self, *_args, **_kwargs):
            return 0

    db = SimpleNamespace(query=lambda *_args: Query(), commit=lambda: None)
    monkeypatch.setattr("app.utils.mailer.send_email", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("duplicate send")))

    notification_delivery._deliver(db, 42)

    assert row.status == "processing"
    assert row.attempt_count == 1


def _delivery_session():
    engine = create_engine("sqlite://")
    NotificationDelivery.__table__.create(engine)
    return Session(engine)


def test_atomic_claim_records_smtp_acceptance(monkeypatch):
    db = _delivery_session()
    row = NotificationDelivery(event_type="booking_created", entity_type="booking", entity_id=1,
        recipient_type="customer", recipient_email="a@example.test", template_key="booking_confirmation",
        payload_json={"values": {}, "fallback_subject": "Subject", "fallback_html": "<p>Body</p>"},
        status="pending", attempt_count=0, idempotency_key="claim-success")
    db.add(row); db.commit()
    monkeypatch.setattr("app.utils.email_templates.render_database_email", lambda *_args: ("Subject", "<p>Body</p>"))
    monkeypatch.setattr("app.utils.mailer.send_email", lambda *_args, **_kwargs: SimpleNamespace(ok=True, error=None))

    notification_delivery._deliver(db, row.id)
    db.refresh(row)

    assert row.status == "smtp_accepted"
    assert row.attempt_count == 1
    assert row.smtp_accepted_at is not None
    assert row.lease_token is None


def test_failed_claim_uses_backoff_then_exhausts(monkeypatch):
    db = _delivery_session()
    row = NotificationDelivery(event_type="booking_created", entity_type="booking", entity_id=2,
        recipient_type="customer", recipient_email="b@example.test", template_key="booking_confirmation",
        payload_json={"values": {}, "fallback_subject": "Subject", "fallback_html": "<p>Body</p>"},
        status="pending", attempt_count=2, idempotency_key="claim-fail")
    db.add(row); db.commit()
    monkeypatch.setattr("app.utils.email_templates.render_database_email", lambda *_args: ("Subject", "<p>Body</p>"))
    monkeypatch.setattr("app.utils.mailer.send_email", lambda *_args, **_kwargs: SimpleNamespace(ok=False, error="smtp unavailable"))

    notification_delivery._deliver(db, row.id)
    db.refresh(row)

    assert row.status == "exhausted"
    assert row.attempt_count == 3
    assert row.exhausted_at is not None
    assert "smtp unavailable" in row.error_message


def test_legacy_stale_delivery_without_payload_requires_manual_review():
    from datetime import timedelta
    from app.utils.money import utcnow

    db = _delivery_session()
    row = NotificationDelivery(event_type="legacy", entity_type="booking", entity_id=3,
        recipient_type="customer", recipient_email="c@example.test", template_key="legacy",
        payload_json=None, status="failed", attempt_count=0, idempotency_key="legacy-no-payload",
        next_attempt_at=utcnow() - timedelta(minutes=1))
    db.add(row); db.commit()

    assert notification_delivery.retry_failed_lifecycle_emails(db) == 0
    db.refresh(row)
    assert row.status == "manual_review"


def test_template_interpolation_rejects_missing_values():
    from app.utils.email_templates import apply_template_values

    try:
        apply_template_values("Booking {{booking_code}} for {{name}}", {"name": "Alex"})
    except ValueError as error:
        assert "booking_code" in str(error)
    else:
        raise AssertionError("missing template variables must fail closed")


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


def test_agent_approval_reserves_a_durable_email_delivery(monkeypatch):
    from app.services import notification_delivery
    from app.utils import notification_triggers

    scheduled = {}
    monkeypatch.setattr(notification_triggers, "notify_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "enqueue_notification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "_user_email", lambda *_args: "agent@example.test")
    monkeypatch.setattr(notification_delivery, "dispatch_lifecycle_email", lambda *args, **kwargs: scheduled.update(args=args, kwargs=kwargs))

    background_tasks = object()
    notification_triggers.notify_agent_approved(
        SimpleNamespace(flush=lambda: None),
        agent_id=19,
        agent_name="Example Agent",
        user_id=28,
        background_tasks=background_tasks,
    )

    assert scheduled["kwargs"]["event"] == "agent_account_approved"
    assert scheduled["kwargs"]["entity_type"] == "agent"
    assert scheduled["kwargs"]["entity_id"] == 19
    assert scheduled["kwargs"]["recipient_email"] == "agent@example.test"
    assert scheduled["kwargs"]["background_tasks"] is background_tasks
    assert scheduled["kwargs"]["values"]["login_url"].endswith("/agent-portal/login")


def test_affiliate_approval_reserves_a_durable_email_delivery(monkeypatch):
    from app.services import notification_delivery
    from app.utils import notification_triggers

    scheduled = {}
    monkeypatch.setattr(notification_triggers, "notify_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "enqueue_notification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "_user_email", lambda *_args: "affiliate@example.test")
    monkeypatch.setattr(notification_delivery, "dispatch_lifecycle_email", lambda *args, **kwargs: scheduled.update(args=args, kwargs=kwargs))

    background_tasks = object()
    notification_triggers.notify_affiliate_approved(
        SimpleNamespace(flush=lambda: None),
        affiliate_id=20,
        affiliate_name="Example Affiliate",
        user_id=29,
        background_tasks=background_tasks,
    )

    assert scheduled["kwargs"]["event"] == "affiliate_account_approved"
    assert scheduled["kwargs"]["entity_type"] == "affiliate"
    assert scheduled["kwargs"]["entity_id"] == 20
    assert scheduled["kwargs"]["recipient_email"] == "affiliate@example.test"
    assert scheduled["kwargs"]["background_tasks"] is background_tasks
    assert scheduled["kwargs"]["values"]["login_url"].endswith("/affiliate-portal/login")


def test_affiliate_lifecycle_events_use_durable_delivery(monkeypatch):
    from app.services import notification_delivery
    from app.utils import notification_triggers

    scheduled = []
    monkeypatch.setattr(notification_triggers, "notify_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "enqueue_notification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "_user_email", lambda *_args: "affiliate@example.test")
    monkeypatch.setattr(notification_delivery, "dispatch_lifecycle_email", lambda *args, **kwargs: scheduled.append(kwargs))

    background_tasks = object()
    db = SimpleNamespace(flush=lambda: None)
    notification_triggers.notify_affiliate_rejected(db, affiliate_id=21, affiliate_name="Example Affiliate", rejection_reason="Details required", user_id=29, background_tasks=background_tasks)
    notification_triggers.notify_affiliate_activated(db, affiliate_id=21, affiliate_name="Example Affiliate", user_id=29, background_tasks=background_tasks)
    notification_triggers.notify_affiliate_suspended(db, affiliate_id=21, affiliate_name="Example Affiliate", reason="Compliance review", user_id=29, background_tasks=background_tasks)

    assert [event["event"] for event in scheduled] == [
        "affiliate_account_rejected",
        "affiliate_account_reactivated",
        "affiliate_account_suspended",
    ]
    assert all(event["recipient_email"] == "affiliate@example.test" for event in scheduled)
    assert all(event["background_tasks"] is background_tasks for event in scheduled)


def test_supplier_and_agent_registration_reserve_durable_admin_deliveries(monkeypatch):
    """New partner applications must remain retryable if SMTP is unavailable."""
    from app.services import notification_delivery
    from app.utils import notification_triggers

    scheduled = []
    monkeypatch.setattr(notification_triggers, "notify_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notification_triggers, "admin_notification_recipients", lambda *_args: {"ops@example.test"})
    monkeypatch.setattr(notification_delivery, "dispatch_lifecycle_email", lambda *args, **kwargs: scheduled.append(kwargs) or True)

    background_tasks = object()
    db = SimpleNamespace(flush=lambda: None)
    notification_triggers.notify_supplier_registered(
        db, supplier_id=31, supplier_name="Example Supplier", background_tasks=background_tasks
    )
    notification_triggers.notify_agent_registered(
        db, agent_id=32, agent_name="Example Agent", background_tasks=background_tasks
    )

    assert [event["event"] for event in scheduled] == ["supplier_registered", "agent_registered"]
    assert [event["recipient_email"] for event in scheduled] == ["ops@example.test", "ops@example.test"]
    assert all(event["background_tasks"] is background_tasks for event in scheduled)


def test_every_runtime_rendered_auth_template_has_a_seed_default():
    """Avoid silently falling back when an auth email is made editable."""
    from app.services.email_templates import DEFAULT_EMAIL_TEMPLATES

    template_keys = {template["key"] for template in DEFAULT_EMAIL_TEMPLATES}
    assert {
        "email_verification",
        "otp_login",
        "password_reset",
        "password_changed",
        "registration_password_created",
        "user_created",
        "account_approved",
        "account_reactivated",
    }.issubset(template_keys)


def test_agent_commission_emails_have_editable_plain_language_templates():
    """Commission decisions must not fall back to ad-hoc HTML outside the CMS."""
    from app.services.email_templates import DEFAULT_EMAIL_TEMPLATES

    templates = {template["key"]: template for template in DEFAULT_EMAIL_TEMPLATES}
    assert {
        "agent_commission_requested",
        "agent_commission_approved",
        "agent_commission_rejected",
    }.issubset(templates)
    for key in (
        "agent_commission_requested",
        "agent_commission_approved",
        "agent_commission_rejected",
    ):
        assert templates[key]["subject"].strip()
        assert templates[key]["body"].strip()
        assert "{{agent_name}}" in templates[key]["body"]
