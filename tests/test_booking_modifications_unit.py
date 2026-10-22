from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.schemas.bookings import BookingModificationCreate, BookingUpdate
from app.services import booking_modifications
from app.services import bookings


def _booking():
    return SimpleNamespace(id=7, booking_code="TV-7", tour_name="Test Tour")


def test_admin_cannot_masquerade_as_modification_requester(monkeypatch):
    monkeypatch.setattr(bookings, "get_booking_by_id", lambda *_args, **_kwargs: _booking())
    monkeypatch.setattr(bookings, "_ensure_booking_access", lambda *_args: None)
    actor = SimpleNamespace(id=1, user_type="ADMIN")
    data = BookingModificationCreate(proposed_changes=BookingUpdate(notes="change"), reason="Please change notes")

    with pytest.raises(HTTPException) as error:
        booking_modifications.create_modification_request(SimpleNamespace(), 7, data, actor)

    assert error.value.status_code == 403


def test_travel_date_request_must_be_atomic_and_separate(monkeypatch):
    monkeypatch.setattr(bookings, "get_booking_by_id", lambda *_args, **_kwargs: _booking())
    monkeypatch.setattr(bookings, "_ensure_booking_access", lambda *_args: None)
    actor = SimpleNamespace(id=2, user_type="CUSTOMER")
    data = BookingModificationCreate(
        proposed_changes=BookingUpdate(tour_date="2027-01-10", notes="also change notes"),
        reason="Move my trip and update notes",
    )

    with pytest.raises(HTTPException) as error:
        booking_modifications.create_modification_request(SimpleNamespace(), 7, data, actor)

    assert error.value.status_code == 422
    assert "separately" in error.value.detail
