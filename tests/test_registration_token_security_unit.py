from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import auth


def token_user(**overrides):
    values = {
        "id": 7,
        "email": "user@example.com",
        "name": "User",
        "user_type": "CUSTOMER",
        "account_status": "PENDING_EMAIL_VERIFICATION",
        "email_verification_token": "old-hash",
        "email_verification_expires_at": datetime.utcnow() + timedelta(minutes=10),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def db_returning(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def test_expired_verification_token_is_rejected(monkeypatch):
    user = token_user(email_verification_expires_at=datetime.utcnow() - timedelta(seconds=1))
    monkeypatch.setattr(auth, "hash_reset_token", lambda _token: "old-hash")
    with pytest.raises(HTTPException, match="Invalid or expired verification link"):
        auth._registration_token_user(db_returning(user), "raw-token")


def test_used_verification_token_cannot_be_reused(monkeypatch):
    user = token_user(account_status="ACTIVE")
    monkeypatch.setattr(auth, "hash_reset_token", lambda _token: "old-hash")
    with pytest.raises(HTTPException, match="already been used"):
        auth._registration_token_user(db_returning(user), "raw-token")


def test_resend_replaces_the_previous_token(monkeypatch):
    user = token_user()
    db = db_returning(user)
    monkeypatch.setattr(auth, "create_password_reset_token", lambda: ("new-raw", "new-hash"))
    send = MagicMock()
    monkeypatch.setattr(auth, "send_email_verification", send)

    assert auth.resend_registration_verification(db, user.email, "/customer/dashboard") is True
    assert user.email_verification_token == "new-hash"
    assert user.email_verification_token != "old-hash"
    send.assert_called_once_with(db, user, "new-raw", "/customer/dashboard")
