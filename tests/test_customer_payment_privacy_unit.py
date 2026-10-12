from app.services import payments


def test_customer_payment_history_hides_internal_payment_identifiers(monkeypatch):
    monkeypatch.setattr(payments, "get_payments", lambda *_args, **_kwargs: {
        "items": [{"id": 44, "payment_code": "PAY-44", "booking_id": 43, "booking_code": "TVAC-43"}],
        "total": 1,
    })

    result = payments.get_customer_payments(object(), customer_id=16)

    assert result["items"] == [{"booking_id": 43, "booking_code": "TVAC-43"}]
