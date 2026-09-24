"""Low-level Viator Partner API transport.

Sync httpx on purpose: the rest of this backend is sync FastAPI + sync
SQLAlchemy (routes run in the threadpool), and the previous Viator code
already used sync httpx - an async client here would need every caller to
become async just for this module.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from app.integrations.viator.exceptions import (
    ViatorAccessDenied,
    ViatorAuthError,
    ViatorBadRequest,
    ViatorError,
    ViatorNotConfigured,
    ViatorNotFound,
    ViatorRateLimited,
    ViatorUnavailable,
)

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://api.sandbox.viator.com/partner"
PRODUCTION_BASE_URL = "https://api.viator.com/partner"
# Partner API v2 is selected through the Accept header.
ACCEPT_HEADER = "application/json;version=2.0"

MAX_RETRIES = 2  # so at most 3 attempts in total - never loops forever
MAX_RETRY_AFTER_SECONDS = 10.0
_RETRYABLE_STATUSES = {429, 502, 503, 504}


def base_url_for(env: str, override: str = "") -> str:
    if override.strip():
        return override.strip().rstrip("/")
    return PRODUCTION_BASE_URL if (env or "").strip().lower() == "production" else SANDBOX_BASE_URL


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass  # HTTP-date form - fall back to backoff
    # 0.5s, 1s (+ jitter) - bounded exponential backoff
    return min(0.5 * (2 ** attempt) + random.uniform(0, 0.25), MAX_RETRY_AFTER_SECONDS)


def _error_for(response: httpx.Response) -> ViatorError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    tracking_id = body.get("trackingId") if isinstance(body, dict) else None
    message = (body.get("message") if isinstance(body, dict) else None) or response.reason_phrase
    status = response.status_code
    cls = {
        400: ViatorBadRequest,
        401: ViatorAuthError,
        403: ViatorAccessDenied,
        404: ViatorNotFound,
        429: ViatorRateLimited,
    }.get(status, ViatorUnavailable if status >= 500 else ViatorError)
    return cls(f"HTTP {status}: {message}", status_code=status, tracking_id=tracking_id)


class ViatorClient:
    def __init__(self, api_key: str, base_url: str, *, timeout: float = 15.0, language: str = "en-US"):
        if not api_key:
            raise ViatorNotConfigured("Viator API key is not set")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.language = language

    def _headers(self) -> dict[str, str]:
        # Built server-side only; never sent to or logged for the browser.
        return {
            "exp-api-key": self._api_key,
            "Accept": ACCEPT_HEADER,
            "Accept-Language": self.language,
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, *, json: Any = None, params: dict | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: ViatorError | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=self.timeout) as http:
                    response = http.request(method, url, headers=self._headers(), json=json, params=params)
            except httpx.TimeoutException as exc:
                last_error = ViatorUnavailable(f"Timeout calling {path}: {type(exc).__name__}")
            except httpx.HTTPError as exc:
                last_error = ViatorUnavailable(f"Network error calling {path}: {type(exc).__name__}")
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ViatorUnavailable(f"Invalid JSON from {path}") from exc
                last_error = _error_for(response)
                if response.status_code not in _RETRYABLE_STATUSES:
                    break
                if attempt < MAX_RETRIES:
                    delay = _retry_delay(attempt, response.headers.get("Retry-After"))
                    logger.warning("Viator %s %s -> %s, retrying in %.1fs (attempt %d)", method, path, response.status_code, delay, attempt + 1)
                    time.sleep(delay)
                continue
            if attempt < MAX_RETRIES:
                time.sleep(_retry_delay(attempt, None))

        assert last_error is not None
        # Safe to log: status, Viator's message and tracking id - no headers/key.
        logger.error(
            "Viator %s %s failed: %s (code=%s, trackingId=%s)",
            method, path, last_error.detail, last_error.code, last_error.tracking_id,
        )
        raise last_error

    # --- endpoints -------------------------------------------------------
    def get_destinations(self) -> dict:
        return self.request("GET", "/destinations")

    def search_products(self, payload: dict) -> dict:
        return self.request("POST", "/products/search", json=payload)
