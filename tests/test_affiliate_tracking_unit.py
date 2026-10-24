from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.affiliate_tracking import _completed_booking_count, is_booking_payout_eligible


def test_link_booking_count_includes_only_completed_tours():
    conversions = [
        SimpleNamespace(booking=SimpleNamespace(booking_status="confirmed")),
        SimpleNamespace(booking=SimpleNamespace(booking_status="ongoing")),
        SimpleNamespace(booking=SimpleNamespace(booking_status="completed")),
        SimpleNamespace(booking=SimpleNamespace(booking_status="cancelled")),
        SimpleNamespace(booking=None),
    ]

    assert _completed_booking_count(conversions) == 1


def test_commission_is_payable_only_24_hours_after_tour_end():
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    eligible = SimpleNamespace(
        booking_status="completed",
        tour_end_date=now - timedelta(hours=24),
    )
    too_soon = SimpleNamespace(
        booking_status="completed",
        tour_end_date=now - timedelta(hours=23, minutes=59),
    )
    missing_end_time = SimpleNamespace(booking_status="completed", tour_end_date=None)

    assert is_booking_payout_eligible(eligible, now=now)
    assert not is_booking_payout_eligible(too_soon, now=now)
    assert not is_booking_payout_eligible(missing_end_time, now=now)
