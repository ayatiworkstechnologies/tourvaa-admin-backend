"""Changing a password (any portal) signs the account out of every device:
access + refresh tokens die, sessions are revoked, push subscriptions are
removed, unused reset links stop working, and the new password works."""
from __future__ import annotations

import requests

from tests.conftest import BASE_URL, create_active_account, login_with_retry, skip_if_readonly, unique, unique_phone

OLD = "OldPass@123"
NEW = "NewPass@456"


class Device:
    """A browser-like client: cookie session + the CSRF double-submit header."""

    def __init__(self, email: str, password: str):
        self.http = requests.Session()
        r = self.http.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password, "client_type": "web-cookie"}, timeout=15)
        assert r.status_code == 200, r.text

    def _headers(self):
        token = self.http.cookies.get("tourvaa_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def get(self, path):
        return self.http.get(f"{BASE_URL}{path}", timeout=15)

    def post(self, path, json=None):
        return self.http.post(f"{BASE_URL}{path}", json=json or {}, headers=self._headers(), timeout=15)


def _db_state(user_id: int):
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models.notifications import PushSubscription
    from app.models.sessions import UserSession
    from app.models.users import User

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        return {
            "active_sessions": db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.status == "active").count(),
            "push_subscriptions": db.query(PushSubscription).filter(PushSubscription.user_id == user_id).count(),
            "reset_token": user.reset_password_token,
        }
    finally:
        db.close()


def _set_reset_token(user_id: int):
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models.users import User

    db = SessionLocal()
    try:
        db.get(User, user_id).reset_password_token = "pending-reset-link-hash"
        db.commit()
    finally:
        db.close()


def _delete_user(user_id: int):
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.services.users import delete_user

    db = SessionLocal()
    try:
        delete_user(db, user_id)
    except Exception:
        db.rollback()
    finally:
        db.close()


@skip_if_readonly()
def test_customer_password_change_signs_out_every_device():
    email = f"{unique('pwreset')}@example.test"
    user = create_active_account("customer", "CUSTOMER", "Pw Reset Tester", email, unique_phone(), OLD)
    try:
        device_a = Device(email, OLD)
        device_b = Device(email, OLD)
        assert device_b.get("/auth/me").status_code == 200

        # Device B has browser push on; an old "forgot password" link is pending.
        r = device_b.post("/notifications/push/subscribe", {"endpoint": f"https://push.example.test/{unique('b')}", "p256dh": "k", "auth": "a"})
        assert r.status_code == 200, r.text
        _set_reset_token(user.id)
        before = _db_state(user.id)
        assert before["active_sessions"] >= 2 and before["push_subscriptions"] == 1

        r = device_a.post("/customer/change-password", {"current_password": OLD, "new_password": NEW})
        assert r.status_code == 200, r.text

        # Every device is out - including a refresh attempt.
        for device in (device_a, device_b):
            assert device.get("/auth/me").status_code == 401
            assert device.post("/auth/refresh-token", {"client_type": "web-cookie"}).status_code == 401

        after = _db_state(user.id)
        assert after == {"active_sessions": 0, "push_subscriptions": 0, "reset_token": None}

        # Old password rejected, new one works.
        assert login_with_retry(email, OLD).status_code in (400, 401)
        assert login_with_retry(email, NEW).status_code == 200
    finally:
        _delete_user(user.id)
