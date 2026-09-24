"""Web push: queued with the transaction, sent only after commit, expired
subscriptions cleaned up, long endpoints accepted, public key served."""
from __future__ import annotations

import requests

import app.main  # noqa: F401 - registers every model
from app.database import SessionLocal
from app.models.notifications import NotificationLog, PushSubscription
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
        assert calls == [(1, "T", "M")]
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


def test_gone_subscriptions_are_removed_others_kept(monkeypatch):
    db = SessionLocal()
    gone = push.save_subscription(db, endpoint="https://push.example.test/gone-" + "x" * 600, p256dh="k", auth="a")
    alive = push.save_subscription(db, endpoint="https://push.example.test/alive", p256dh="k", auth="a")
    results = {gone.id: "gone", alive.id: "failed"}
    monkeypatch.setattr(push, "send_push", lambda sub, **_: results[sub.id])
    try:
        assert push._deliver(db, [gone, alive], title="t", body="b") == {"sent": 0, "failed": 2}
        ids = {s.id for s in db.query(PushSubscription).filter(PushSubscription.id.in_([gone.id, alive.id]))}
        assert ids == {alive.id}  # only the 404/410 one is deleted
    finally:
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


def test_public_key_endpoint():
    r = requests.get(f"{BASE_URL}/notifications/push/public-key", timeout=10)
    assert r.status_code == 200
    key = r.json()["data"]["public_key"]
    assert key == "" or len(key) == 87  # base64url P-256 public key
