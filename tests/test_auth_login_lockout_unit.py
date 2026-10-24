from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import auth
from app.utils.money import utcnow


def _login_data():
    return SimpleNamespace(
        login_identifier="locked@example.com",
        password="password",
        client_type="web",
        device_id=None,
        device_name=None,
    )


def _db_returning(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def _user(*, locked_until):
    return SimpleNamespace(
        id=7,
        email="locked@example.com",
        phone=None,
        mobile_number=None,
        password="hashed-password",
        locked_until=locked_until,
        failed_login_attempts=5,
        user_type="ADMIN",
        email_verified_at=None,
        two_factor_enabled=False,
    )


def test_login_rejects_active_naive_mysql_lock_timestamp(monkeypatch):
    # MySQL returns DateTime(timezone=True) columns without tzinfo.
    user = _user(locked_until=(utcnow() + timedelta(minutes=5)).replace(tzinfo=None))
    db = _db_returning(user)
    monkeypatch.setattr(auth, "_record_login_history", MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        auth.login_user(db, _login_data())

    assert exc_info.value.status_code == 423
    db.commit.assert_called_once()


def test_login_accepts_expired_naive_mysql_lock_timestamp(monkeypatch):
    user = _user(locked_until=(utcnow() - timedelta(minutes=5)).replace(tzinfo=None))
    db = _db_returning(user)
    monkeypatch.setattr(auth, "verify_password", lambda *_args: True)
    finalize = MagicMock(return_value={"status": "success"})
    monkeypatch.setattr(auth, "_finalize_login", finalize)

    result = auth.login_user(db, _login_data())

    assert result == {"status": "success"}
    assert user.locked_until is None
    assert user.failed_login_attempts == 0
    finalize.assert_called_once_with(db, user, _login_data(), request=None)


def _active_user(user_type: str):
    return SimpleNamespace(
        id=17,
        email="single-device@example.com",
        user_type=user_type,
        account_status="ACTIVE",
        is_active=True,
        token_version=4,
        last_login_at=None,
    )


def _finalize_login(monkeypatch, user_type: str, role_slug: str):
    db = MagicMock()
    session = SimpleNamespace(session_id="new-session", current_refresh_jti=None)
    user = _active_user(user_type)
    monkeypatch.setattr(auth, "get_auth_user_payload", lambda _db, _user: {"role": {"slug": role_slug}})
    monkeypatch.setattr(auth, "create_session", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(auth, "create_token", lambda claims, **_kwargs: f"token-{claims.get('token_type', 'access')}")
    monkeypatch.setattr(auth, "_record_login_history", MagicMock())
    monkeypatch.setattr(auth, "log_audit", MagicMock())
    result = auth._finalize_login(db, user, _login_data())
    return db, user, result


def test_customer_login_revokes_prior_sessions_and_rotates_token_version(monkeypatch):
    db, user, result = _finalize_login(monkeypatch, "CUSTOMER", "customer")

    assert result["session_id"] == "new-session"
    db.query.return_value.filter.return_value.update.assert_called_once()
    values = db.query.return_value.filter.return_value.update.call_args.args[0]
    assert values["status"] == "revoked"
    assert user.token_version == 5


def test_supplier_login_preserves_existing_multi_device_sessions(monkeypatch):
    db, user, result = _finalize_login(monkeypatch, "SUPPLIER", "supplier")

    assert result["session_id"] == "new-session"
    db.query.return_value.filter.return_value.update.assert_not_called()
    assert user.token_version == 4
