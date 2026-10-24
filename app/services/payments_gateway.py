"""
Stripe and PayPal gateway helpers.
Both gateways read credentials from the database PaymentSetting table.
"""

import base64
import logging
import time
from typing import Optional

import requests as http_requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _gateway_error_code(response) -> str:
    """Return safe provider diagnostics without logging response URLs or data."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("code"):
                return str(error["code"])
            if payload.get("name"):
                return str(payload["name"])
    except (ValueError, TypeError, AttributeError):
        pass
    return "unknown"


def normalize_paypal_mode(mode: str | None) -> str:
    """Return PayPal's two supported environment names.

    Older local seed data used ``test``. It is equivalent to PayPal sandbox,
    but normalizing it prevents a case-sensitive ``LIVE``/``Sandbox`` value
    from silently selecting the wrong API host.
    """
    value = (mode or "sandbox").strip().lower()
    if value in {"sandbox", "test"}:
        return "sandbox"
    if value == "live":
        return "live"
    raise ValueError("PayPal mode must be 'sandbox' or 'live'")

# helpers to load gateway credentials


def _load_setting(db: Session, provider: str) -> "PaymentSetting | None":
    from app.models.settings import PaymentSetting

    return db.query(PaymentSetting).filter(
        PaymentSetting.provider_name == provider,
        PaymentSetting.is_enabled == 1,
    ).first()


# stripe


class StripeGateway:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.base_url = "https://api.stripe.com/v1"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def create_checkout_session(self, *, amount_cents: int, currency: str, booking_id: int, success_url: str, cancel_url: str, customer_email: Optional[str] = None, idempotency_key: Optional[str] = None, hold_funds: bool = True) -> dict:
        payload = {
            "mode": "payment",
            "payment_method_types[]": "card",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": amount_cents,
            "line_items[0][price_data][product_data][name]": f"Booking #{booking_id}",
            "line_items[0][quantity]": 1,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata[booking_id]": booking_id,
        }
        # Do not charge the card at Checkout.  A manual-capture PaymentIntent
        # leaves the payment in requires_capture after customer approval.
        if hold_funds:
            payload["payment_intent_data[capture_method]"] = "manual"
        if customer_email:
            payload["customer_email"] = customer_email

        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp = http_requests.post(f"{self.base_url}/checkout/sessions", data=payload, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("Stripe create_checkout_session failed: status=%s code=%s", resp.status_code, _gateway_error_code(resp))
            raise HTTPException(status_code=502, detail=f"Stripe error: {resp.json().get('error', {}).get('message', 'Unknown error')}")
        return resp.json()

    def retrieve_session(self, session_id: str) -> dict:
        resp = http_requests.get(f"{self.base_url}/checkout/sessions/{session_id}", headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to retrieve Stripe session")
        return resp.json()

    def retrieve_payment_intent(self, payment_intent_id: str) -> dict:
        resp = http_requests.get(f"{self.base_url}/payment_intents/{payment_intent_id}", headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to retrieve Stripe payment intent")
        return resp.json()

    def capture_payment_intent(self, payment_intent_id: str, amount_cents: int, idempotency_key: Optional[str] = None) -> dict:
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        resp = http_requests.post(f"{self.base_url}/payment_intents/{payment_intent_id}/capture", data={"amount_to_capture": amount_cents}, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("Stripe capture_payment_intent error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"Stripe capture error: {resp.json().get('error', {}).get('message', 'Unknown error')}")
        return resp.json()

    def cancel_payment_intent(self, payment_intent_id: str, idempotency_key: Optional[str] = None) -> dict:
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        resp = http_requests.post(f"{self.base_url}/payment_intents/{payment_intent_id}/cancel", data={}, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("Stripe cancel_payment_intent error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"Stripe authorization release error: {resp.json().get('error', {}).get('message', 'Unknown error')}")
        return resp.json()

    def create_refund(self, payment_intent_id: str, amount_cents: int, reason: str = "requested_by_customer", idempotency_key: Optional[str] = None) -> dict:
        payload = {
            "payment_intent": payment_intent_id,
            "amount": amount_cents,
            "reason": reason if reason in ("duplicate", "fraudulent", "requested_by_customer") else "requested_by_customer",
        }
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = http_requests.post(f"{self.base_url}/refunds", data=payload, headers=headers, timeout=15)
            except http_requests.exceptions.RequestException as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))
                continue
            if resp.status_code in (200, 201):
                return resp.json()
            if resp.status_code >= 500:
                last_error = HTTPException(status_code=502, detail="Stripe refund error: gateway unavailable")
                time.sleep(0.5 * (attempt + 1))
                continue
            logger.error("Stripe refund error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"Stripe refund error: {resp.json().get('error', {}).get('message', 'Unknown')}")
        logger.error("Stripe refund failed after retries: %s", last_error)
        raise HTTPException(status_code=502, detail="Stripe refund failed after retries; the gateway may be temporarily unavailable")

    def construct_event(self, payload: bytes, sig_header: str, webhook_secret: str) -> dict:
        """Manually verify Stripe webhook signature (HMAC-SHA256)."""
        import hashlib
        import hmac

        parts = {k: v for part in sig_header.split(",") for k, v in [part.split("=", 1)]}
        timestamp = parts.get("t", "0")
        received_sig = parts.get("v1", "")

        signed_payload = f"{timestamp}.{payload.decode()}"
        expected_sig = hmac.new(webhook_secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()

        # Reject stale webhooks (>5 min)
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(status_code=400, detail="Stripe webhook timestamp too old")
        if not hmac.compare_digest(expected_sig, received_sig):
            raise HTTPException(status_code=400, detail="Stripe webhook signature invalid")

        import json
        return json.loads(payload)


# paypal


class PayPalGateway:
    def __init__(self, client_id: str, client_secret: str, mode: str = "sandbox"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.mode = normalize_paypal_mode(mode)
        self.base_url = "https://api-m.paypal.com" if self.mode == "live" else "https://api-m.sandbox.paypal.com"
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 30:
            return self._access_token
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = http_requests.post(
            f"{self.base_url}/v1/oauth2/token",
            headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
            data="grant_type=client_credentials",
            timeout=15,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="PayPal authentication failed")
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._access_token

    def _headers(self, idempotency_key: Optional[str] = None) -> dict:
        h = {"Authorization": f"Bearer {self._get_access_token()}", "Content-Type": "application/json"}
        if idempotency_key:
            h["PayPal-Request-Id"] = idempotency_key
        return h

    def create_order(self, *, amount: str, currency: str, booking_id: int, return_url: str, cancel_url: str, idempotency_key: Optional[str] = None, hold_funds: bool = True) -> dict:
        payload = {
            "intent": "AUTHORIZE" if hold_funds else "CAPTURE",
            "purchase_units": [{"reference_id": str(booking_id), "amount": {"currency_code": currency.upper(), "value": amount}, "description": f"Booking #{booking_id}"}],
            "application_context": {"return_url": return_url, "cancel_url": cancel_url, "brand_name": "Tourvaa", "user_action": "PAY_NOW"},
        }
        resp = http_requests.post(f"{self.base_url}/v2/checkout/orders", json=payload, headers=self._headers(idempotency_key), timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("PayPal create_order failed: status=%s code=%s", resp.status_code, _gateway_error_code(resp))
            raise HTTPException(status_code=502, detail=f"PayPal error: {resp.json().get('message', 'Unknown')}")
        return resp.json()

    def authorize_order(self, order_id: str, idempotency_key: Optional[str] = None) -> dict:
        resp = http_requests.post(f"{self.base_url}/v2/checkout/orders/{order_id}/authorize", json={}, headers=self._headers(idempotency_key), timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("PayPal authorize_order error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"PayPal authorization error: {resp.json().get('message', 'Unknown')}")
        return resp.json()

    def capture_authorization(self, authorization_id: str, amount: str, currency: str, idempotency_key: Optional[str] = None) -> dict:
        payload = {"amount": {"value": amount, "currency_code": currency.upper()}, "final_capture": True}
        resp = http_requests.post(f"{self.base_url}/v2/payments/authorizations/{authorization_id}/capture", json=payload, headers=self._headers(idempotency_key), timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("PayPal capture_authorization error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"PayPal capture error: {resp.json().get('message', 'Unknown')}")
        return resp.json()

    def void_authorization(self, authorization_id: str, idempotency_key: Optional[str] = None) -> dict:
        resp = http_requests.post(f"{self.base_url}/v2/payments/authorizations/{authorization_id}/void", json={}, headers=self._headers(idempotency_key), timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("PayPal void_authorization error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"PayPal authorization release error: {resp.json().get('message', 'Unknown')}")
        return resp.json()

    def capture_order(self, order_id: str, idempotency_key: Optional[str] = None) -> dict:
        resp = http_requests.post(f"{self.base_url}/v2/checkout/orders/{order_id}/capture", json={}, headers=self._headers(idempotency_key), timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("PayPal capture_order error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"PayPal capture error: {resp.json().get('message', 'Unknown')}")
        return resp.json()

    def verify_webhook_signature(self, *, headers: dict, webhook_id: str, event_body: dict) -> bool:
        """Verify a PayPal webhook via PayPal's own verify-webhook-signature
        API (the officially recommended server-side approach - it avoids
        having to implement certificate-chain/CRL validation ourselves).
        Returns True only if PayPal itself confirms the signature is valid.
        """
        def _header(name: str) -> str:
            # Starlette Headers are case-insensitive, but plain dicts (as used
            # in tests) may not be - check a couple of common casings.
            return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper()) or ""

        transmission_id = _header("PAYPAL-TRANSMISSION-ID")
        transmission_time = _header("PAYPAL-TRANSMISSION-TIME")
        transmission_sig = _header("PAYPAL-TRANSMISSION-SIG")
        cert_url = _header("PAYPAL-CERT-URL")
        auth_algo = _header("PAYPAL-AUTH-ALGO")

        if not all([transmission_id, transmission_time, transmission_sig, cert_url, auth_algo, webhook_id]):
            logger.error("PayPal webhook verification: missing required transmission headers or webhook_id")
            return False

        payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": event_body,
        }
        try:
            resp = http_requests.post(f"{self.base_url}/v1/notifications/verify-webhook-signature", json=payload, headers=self._headers(), timeout=15)
        except Exception:
            # Fail closed: an OAuth failure, network error, or anything else
            # going wrong while trying to verify must never be treated as
            # "verified" - an unverifiable webhook is a rejected webhook.
            logger.exception("PayPal webhook verification request failed")
            return False
        if resp.status_code != 200:
            logger.error("PayPal webhook verification call failed: %s", resp.text)
            return False
        try:
            return resp.json().get("verification_status") == "SUCCESS"
        except Exception:
            logger.exception("PayPal webhook verification returned an unparsable response")
            return False

    def create_refund(self, capture_id: str, amount: str, currency: str, note: str = "Refund", idempotency_key: Optional[str] = None) -> dict:
        payload = {"amount": {"value": amount, "currency_code": currency.upper()}, "note_to_payer": note[:255]}
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = http_requests.post(f"{self.base_url}/v2/payments/captures/{capture_id}/refund", json=payload, headers=self._headers(idempotency_key), timeout=15)
            except http_requests.exceptions.RequestException as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))
                continue
            if resp.status_code in (200, 201):
                return resp.json()
            if resp.status_code >= 500:
                last_error = HTTPException(status_code=502, detail="PayPal refund error: gateway unavailable")
                time.sleep(0.5 * (attempt + 1))
                continue
            logger.error("PayPal refund error: %s", resp.text)
            raise HTTPException(status_code=502, detail=f"PayPal refund error: {resp.json().get('message', 'Unknown')}")
        logger.error("PayPal refund failed after retries: %s", last_error)
        raise HTTPException(status_code=502, detail="PayPal refund failed after retries; the gateway may be temporarily unavailable")


# factory functions - load from db settings


def get_stripe(db: Session) -> StripeGateway:
    from app.utils.crypto import decrypt_secret
    setting = _load_setting(db, "stripe")
    if not setting or not setting.secret_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured or not enabled")
    return StripeGateway(secret_key=decrypt_secret(setting.secret_key))


def get_paypal(db: Session) -> PayPalGateway:
    from app.utils.crypto import decrypt_secret
    setting = _load_setting(db, "paypal")
    if not setting:
        raise HTTPException(status_code=400, detail="PayPal is not configured or not enabled")
    try:
        mode = normalize_paypal_mode(getattr(setting, "mode", "sandbox"))
    except ValueError as error:
        logger.error("PayPal setting has an invalid mode: %s", getattr(setting, "mode", None))
        raise HTTPException(status_code=500, detail="PayPal mode must be sandbox or live") from error
    client_id = getattr(setting, f"{mode}_client_id", None) or setting.public_key
    encrypted_secret = getattr(setting, f"{mode}_secret", None) or setting.secret_key
    if not client_id or not encrypted_secret:
        raise HTTPException(status_code=400, detail=f"PayPal {mode} credentials are not configured")
    return PayPalGateway(client_id=client_id, client_secret=decrypt_secret(encrypted_secret), mode=mode)
