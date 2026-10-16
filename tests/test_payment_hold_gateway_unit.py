from unittest.mock import Mock, patch

from app.services.payments_gateway import PayPalGateway, StripeGateway


def _response(payload):
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    return response


@patch("app.services.payments_gateway.http_requests.post")
def test_stripe_checkout_uses_manual_capture_for_a_payment_hold(post):
    post.return_value = _response({"id": "cs_hold", "url": "https://checkout.example"})
    StripeGateway("sk_test_example").create_checkout_session(
        amount_cents=2500, currency="USD", booking_id=9,
        success_url="https://example.test/success", cancel_url="https://example.test/cancel",
    )
    assert post.call_args.kwargs["data"]["payment_intent_data[capture_method]"] == "manual"


@patch.object(PayPalGateway, "_headers", return_value={})
@patch("app.services.payments_gateway.http_requests.post")
def test_paypal_order_uses_authorize_intent_for_a_payment_hold(post, _headers):
    post.return_value = _response({"id": "order_hold"})
    PayPalGateway("client", "secret").create_order(
        amount="25.00", currency="USD", booking_id=9,
        return_url="https://example.test/success", cancel_url="https://example.test/cancel",
    )
    assert post.call_args.kwargs["json"]["intent"] == "AUTHORIZE"
