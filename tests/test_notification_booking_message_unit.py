from types import SimpleNamespace

from app.services import notifications


def test_booking_conversation_notification_resolves_booking_route(monkeypatch):
    class Query:
        def filter(self, *_args):
            return self

        def scalar(self):
            return 43

        def first(self):
            return SimpleNamespace(role=SimpleNamespace(slug="customer"))

    class Db:
        def query(self, _model):
            return Query()

    assert notifications._notification_booking_id(Db(), "booking_conversation", 17) == 43
    assert notifications._notification_url(Db(), 9, "booking_conversation", 17) == "/customer/bookings/43"


def test_affiliate_conversion_notification_resolves_conversion_route():
    class Query:
        def filter(self, *_args):
            return self

        def first(self):
            return SimpleNamespace(role=SimpleNamespace(slug="affiliate"))

    class Db:
        def query(self, _model):
            return Query()

    assert notifications._notification_url(Db(), 9, "affiliate_conversion", 17) == "/affiliate/conversions"
