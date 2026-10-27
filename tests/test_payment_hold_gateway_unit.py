from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.payments import release_gateway_authorized_payment

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


@patch("app.services.payments.capture_gateway_authorized_payment")
@patch("app.services.payments_gateway.get_stripe")
def test_expired_stripe_hold_reconciles_a_succeeded_intent_instead_of_cancelling(get_stripe, reconcile):
    """A missed webhook must not lead the expiry worker to void captured funds."""
    stripe = Mock()
    stripe.retrieve_payment_intent.return_value = {"status": "succeeded"}
    get_stripe.return_value = stripe
    payment = SimpleNamespace(
        id=23,
        payment_status="authorized",
        gateway="stripe",
        gateway_payment_id="pi_succeeded",
    )

    release_gateway_authorized_payment(Mock(), payment, "Authorization expired before booking confirmation")

    reconcile.assert_called_once()
    stripe.cancel_payment_intent.assert_not_called()
