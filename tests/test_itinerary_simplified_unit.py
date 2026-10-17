from types import SimpleNamespace

from app.schemas.tours import ItineraryPayload
from app.services import tours


class FakeSession:
    def __init__(self):
        self.added = None

    def add(self, obj):
        self.added = obj

    def commit(self):
        pass

    def refresh(self, obj):
        pass


def test_simplified_update_preserves_omitted_legacy_fields(monkeypatch):
    record = SimpleNamespace(start_time="09:00", end_time="10:00", transport_type="Bus", images='["old.jpg"]', day_type="free_day", image_alt_text="Existing alt")
    monkeypatch.setattr(tours, "_child_or_404", lambda *args: record)
    monkeypatch.setattr(tours, "log_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(tours, "maybe_resubmit_for_review", lambda *args: None)
    monkeypatch.setattr(tours, "_ser_itinerary", lambda obj: obj)
    payload = ItineraryPayload(day_number=1, day_title="Madurai", location_name="Madurai")
    tours.update_itinerary(FakeSession(), 1, 1, payload, None)
    assert (record.start_time, record.end_time, record.transport_type, record.images, record.day_type) == ("09:00", "10:00", "Bus", '["old.jpg"]', "free_day")


def test_create_defaults_order_and_image_alt(monkeypatch):
    monkeypatch.setattr(tours, "TourItinerary", SimpleNamespace)
    monkeypatch.setattr(tours, "_require_tour", lambda *args: None)
    monkeypatch.setattr(tours, "log_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(tours, "maybe_resubmit_for_review", lambda *args: None)
    monkeypatch.setattr(tours, "_ser_itinerary", lambda obj: obj)
    db = FakeSession()
    payload = ItineraryPayload(day_number=2, day_title="Temple visit", location_name="Madurai", image="temple.jpg")
    tours.create_itinerary(db, 1, payload, None)
    assert db.added.display_order == 2
    assert db.added.image_alt_text == "Temple visit - Madurai"


def test_explicit_null_and_images_are_updated():
    fields = tours._itinerary_fields(ItineraryPayload(day_number=1, accommodation=None, images=[]), exclude_unset=True)
    assert fields == {"day_number": 1, "accommodation": "", "images": "[]"}
