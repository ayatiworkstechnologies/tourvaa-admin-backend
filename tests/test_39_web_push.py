"""Web push: queued with the transaction, sent only after commit, expired
subscriptions cleaned up, long endpoints accepted, public key served."""
from __future__ import annotations

import requests

import app.main  # noqa: F401 - registers every model
from app.database import SessionLocal
from app.models.notifications import Notification, NotificationLog, PushDeliveryLog, PushSubscription
from app.services import notifications_push as push
from app.services.notifications import enqueue_notification
from tests.conftest import BASE_URL


def _run_worker_inline(monkeypatch, calls):
    """Run the after-commit worker synchronously and record deliveries."""
    class InlineThread:
        def __init__(self, target, args, **_):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(push.threading, "Thread", InlineThread)
    monkeypatch.setattr(push, "is_configured", lambda: True)
    monkeypatch.setattr(push, "_push_worker", lambda items: calls.extend(items))


def test_push_is_sent_after_commit(monkeypatch):
    calls: list = []
    _run_worker_inline(monkeypatch, calls)
    db = SessionLocal()
    try:
        n = enqueue_notification(db, user_id=1, notification_type="push_unit_test", title="T", message="M")
        assert calls == []  # nothing before commit
        db.commit()
        assert calls == [(n.id, 1, "T", "M", "/")]
    finally:
        db.query(NotificationLog).filter(NotificationLog.notification_id == n.id).delete()
        db.delete(n)
        db.commit()
        db.close()


def test_no_push_after_rollback(monkeypatch):
    calls: list = []
    _run_worker_inline(monkeypatch, calls)
    db = SessionLocal()
    try:
        enqueue_notification(db, user_id=1, notification_type="push_unit_test", title="T", message="M")
        db.rollback()
        db.commit()
        assert calls == []
    finally:
        db.close()


def test_generic_entity_notification_keeps_reference_and_safe_action():
    db = SessionLocal()
    notification = None
    try:
        notification = enqueue_notification(
            db, user_id=1, notification_type="push_entity_test", title="Payout requested", message="M",
            entity_type="affiliate_payout", entity_id=987654,
        )
        assert notification.metadata_json == {
            "entity_type": "affiliate_payout", "entity_id": 987654,
            "action_url": "/admin/affiliates/payouts", "action_label": "View details",
        }
    finally:
        db.rollback()
        db.close()


def test_gone_subscriptions_are_deactivated_others_kept(monkeypatch):
    db = SessionLocal()
    gone = push.save_subscription(db, endpoint="https://push.example.test/gone-" + "x" * 600, p256dh="k", auth="a")
    alive = push.save_subscription(db, endpoint="https://push.example.test/alive", p256dh="k", auth="a")
    results = {gone.id: "gone", alive.id: "failed"}
    monkeypatch.setattr(push, "send_push", lambda sub, **_: results[sub.id])
    try:
        assert push._deliver(db, [gone, alive], title="t", body="b") == {"sent": 0, "failed": 2}
        statuses = {s.id: s.is_active for s in db.query(PushSubscription).filter(PushSubscription.id.in_([gone.id, alive.id]))}
        assert statuses == {gone.id: 0, alive.id: 1}
    finally:
        db.query(PushDeliveryLog).filter(PushDeliveryLog.subscription_id.in_([gone.id, alive.id])).delete(synchronize_session=False)
        db.query(PushSubscription).filter(PushSubscription.id == gone.id).delete(synchronize_session=False)
        push.delete_subscription(db, "https://push.example.test/alive")
        db.close()


def test_resubscribing_same_browser_updates_not_duplicates():
    db = SessionLocal()
    endpoint = "https://push.example.test/dup-" + "y" * 700
    try:
        first = push.save_subscription(db, endpoint=endpoint, p256dh="k1", auth="a1")
        second = push.save_subscription(db, endpoint=endpoint, p256dh="k2", auth="a2")
        assert first.id == second.id and second.p256dh == "k2"
    finally:
        push.delete_subscription(db, endpoint)
        db.close()


def test_failed_delivery_retries_same_audit_row(monkeypatch):
    db = SessionLocal()
    endpoint = "https://push.example.test/retry-" + "z" * 600
    notification = Notification(
        user_id=1,
        notification_type="push_retry_test",
        title="Retry title",
        message="Retry body",
        channel="in_app",
        status="sent",
        metadata_json={"action_url": "/admin/bookings/1"},
    )
    db.add(notification)
    db.commit()
    sub = push.save_subscription(db, endpoint=endpoint, p256dh="k", auth="a")
    try:
        monkeypatch.setattr(push, "send_push", lambda *_args, **_kwargs: "failed")
        push._deliver(db, [sub], notification_id=notification.id, recipient_user_id=1, title=notification.title, body=notification.message)
        row = db.query(PushDeliveryLog).filter(PushDeliveryLog.notification_id == notification.id).one()
        assert row.status == "failed" and row.attempt_count == 1

        monkeypatch.setattr(push, "send_push", lambda *_args, **_kwargs: "sent")
        assert push.retry_failed_push_deliveries(db) == {"retried": 1, "sent": 1, "failed": 0, "skipped": 0}
        db.refresh(row)
        assert row.status == "sent" and row.attempt_count == 2
    finally:
        db.query(PushDeliveryLog).filter(PushDeliveryLog.notification_id == notification.id).delete(synchronize_session=False)
        push.delete_subscription(db, endpoint)
        db.query(NotificationLog).filter(NotificationLog.notification_id == notification.id).delete(synchronize_session=False)
        db.delete(notification)
        db.commit()
        db.close()


def test_public_key_endpoint():
    r = requests.get(f"{BASE_URL}/notifications/push/public-key", timeout=10)
    assert r.status_code == 200
    key = r.json()["data"]["public_key"]
    assert key == "" or len(key) == 87  # base64url P-256 public key
