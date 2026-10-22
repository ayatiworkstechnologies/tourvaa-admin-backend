from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.tours import _assert_calendar_date_is_unique


def test_calendar_rejects_a_second_departure_for_the_same_tour_day():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = object()

    with pytest.raises(HTTPException) as exc:
        _assert_calendar_date_is_unique(db, 42, datetime(2027, 3, 15, 9, 30))

    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


def test_calendar_allows_a_date_when_no_other_departure_exists():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    _assert_calendar_date_is_unique(db, 42, datetime(2027, 3, 15))


def test_calendar_date_check_excludes_the_entry_being_edited():
    db = MagicMock()
    query = db.query.return_value.filter.return_value
    query.filter.return_value.first.return_value = None

    _assert_calendar_date_is_unique(db, 42, datetime(2027, 3, 15), exclude_calendar_id=8)

    assert query.filter.called
