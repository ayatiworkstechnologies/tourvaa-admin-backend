from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.schemas.checkout import CheckoutStart
from app.services.checkout import (
    _ensure_session_not_expired,
    _ensure_session_owner,
    start_session,
)
from app.utils.money import utcnow


def session(**overrides):
    values = {
        "id": 1,
        "session_key": "checkout-key",
        "user_id": None,
        "customer_id": None,
        "tour_id": 10,
        "tour_calendar_id": None,
        "step": "travellers",
        "status": "active",
        "data": {},
        "booking_id": None,
        "expires_at": utcnow() + timedelta(hours=1),
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _ExistingSessionQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.row


class _ExistingSessionDb:
    def __init__(self, row):
        self.row = row
        self.committed = False

    def query(self, _model):
        return _ExistingSessionQuery(self.row)

    def commit(self):
        self.committed = True

    def refresh(self, _row):
        pass


def test_guest_can_access_unclaimed_checkout_session():
    _ensure_session_owner(session(), current_user=None)


def test_claimed_checkout_session_rejects_guest():
    with pytest.raises(HTTPException) as exc:
        _ensure_session_owner(session(user_id=7), current_user=None)
    assert exc.value.status_code == 403


def test_claimed_checkout_session_rejects_different_user():
    with pytest.raises(HTTPException) as exc:
        _ensure_session_owner(session(user_id=7), current_user=SimpleNamespace(id=8))
    assert exc.value.status_code == 403


def test_claimed_checkout_session_allows_owner():
    _ensure_session_owner(session(user_id=7), current_user=SimpleNamespace(id=7))


def test_expired_checkout_session_is_gone():
    with pytest.raises(HTTPException) as exc:
        _ensure_session_not_expired(session(expires_at=utcnow() - timedelta(seconds=1)))
    assert exc.value.status_code == 410


def test_active_checkout_session_is_not_expired():
    _ensure_session_not_expired(session())


def test_start_cannot_resume_another_users_session():
    row = session(user_id=7)
    db = _ExistingSessionDb(row)

    with pytest.raises(HTTPException) as exc:
        start_session(
            db,
            CheckoutStart(tour_id=10, session_key=row.session_key),
            current_user=SimpleNamespace(id=8),
        )

    assert exc.value.status_code == 403
    assert db.committed is False


def test_start_cannot_resume_expired_session():
    row = session(expires_at=utcnow() - timedelta(seconds=1))
    db = _ExistingSessionDb(row)

    with pytest.raises(HTTPException) as exc:
        start_session(
            db,
            CheckoutStart(tour_id=10, session_key=row.session_key),
            current_user=None,
        )

    assert exc.value.status_code == 410
    assert db.committed is False
