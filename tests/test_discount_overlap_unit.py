from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.tours import _assert_no_discount_overlap, _discount_dates_overlap


UTC = timezone.utc


class _DiscountQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_conditions):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _DiscountDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *_models):
        return _DiscountQuery(self.rows)


def _discount(**overrides):
    values = {
        "id": 1,
        "discount_name": "Existing supplier offer",
        "changed_by": 2,
        "funded_by": "SUPPLIER",
        "status": "active",
        "start_date": datetime(2026, 10, 1, tzinfo=UTC),
        "end_date": datetime(2026, 10, 31, tzinfo=UTC),
        "discount_scope": "all_tours",
        "tour_id": None,
        "category_id": None,
        "country_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_discount_date_windows_are_inclusive_and_support_open_ended_dates():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 10, 31, tzinfo=UTC)

    assert _discount_dates_overlap(start, end, end, datetime(2026, 11, 2, tzinfo=UTC))
    assert _discount_dates_overlap(None, end, datetime(2026, 9, 30, tzinfo=UTC), None)
    assert not _discount_dates_overlap(start, end, datetime(2026, 11, 1, tzinfo=UTC), None)


def test_same_source_overlapping_promo_or_automatic_discount_is_rejected():
    with pytest.raises(HTTPException, match="overlaps an active discount") as error:
        _assert_no_discount_overlap(
            _DiscountDb([_discount()]),
            start_date=datetime(2026, 10, 15, tzinfo=UTC),
            end_date=datetime(2026, 11, 15, tzinfo=UTC),
            scope="all_tours",
            tour_id=None,
            category_id=None,
            country_id=None,
            funded_by="SUPPLIER",
        )

    assert error.value.status_code == 409


def test_cross_layer_discount_and_non_overlapping_discount_remain_valid():
    supplier_offer = _discount()
    for funded_by, start_date in [
        ("TOURVAA", datetime(2026, 10, 15, tzinfo=UTC)),
        ("SUPPLIER", datetime(2026, 11, 1, tzinfo=UTC)),
    ]:
        _assert_no_discount_overlap(
            _DiscountDb([supplier_offer]),
            start_date=start_date,
            end_date=datetime(2026, 11, 15, tzinfo=UTC),
            scope="all_tours",
            tour_id=None,
            category_id=None,
            country_id=None,
            funded_by=funded_by,
        )


def test_supplier_overlap_validation_ignores_other_tours():
    """A supplier's date validation is only for their current tour."""
    _assert_no_discount_overlap(
        _DiscountDb([_discount(tour_id=99, discount_scope="tour")]),
        start_date=datetime(2026, 10, 15, tzinfo=UTC),
        end_date=datetime(2026, 10, 20, tzinfo=UTC),
        scope="tour",
        tour_id=3,
        category_id=None,
        country_id=None,
        funded_by="SUPPLIER",
        exact_tour_only=True,
    )


def test_creator_overlap_validation_rejects_same_tour():
    with pytest.raises(HTTPException, match="overlaps the active discount"):
        _assert_no_discount_overlap(
            _DiscountDb([_discount(tour_id=3, discount_scope="tour")]),
            start_date=datetime(2026, 10, 15, tzinfo=UTC),
            end_date=datetime(2026, 10, 20, tzinfo=UTC),
            scope="tour",
            tour_id=3,
            category_id=None,
            country_id=None,
            funded_by="SUPPLIER",
            exact_tour_only=True,
            creator_user_id=2,
        )


def test_supplier_overlap_validation_ignores_admin_created_supplier_funded_discount():
    """Funding source is not the same thing as the user who created it."""
    _assert_no_discount_overlap(
        _DiscountDb([_discount(tour_id=3, discount_scope="tour", changed_by=1)]),
        start_date=datetime(2026, 10, 15, tzinfo=UTC),
        end_date=datetime(2026, 10, 20, tzinfo=UTC),
        scope="tour",
        tour_id=3,
        category_id=None,
        country_id=None,
        funded_by="SUPPLIER",
        exact_tour_only=True,
        creator_user_id=2,
    )
