"""Normalised Viator errors.

Each carries a safe, customer-presentable `public_message`; the raw Viator
response body is only ever logged (never returned to the browser), and the
API key is never part of any message.
"""
from __future__ import annotations

UNAVAILABLE_MESSAGE = "Experiences are temporarily unavailable. Please try again."


class ViatorError(Exception):
    status_code: int | None = None
    code = "VIATOR_ERROR"
    public_message = UNAVAILABLE_MESSAGE

    def __init__(self, detail: str = "", *, status_code: int | None = None, tracking_id: str | None = None):
        super().__init__(detail or self.code)
        if status_code is not None:
            self.status_code = status_code
        self.detail = detail
        self.tracking_id = tracking_id


class ViatorNotConfigured(ViatorError):
    code = "NOT_CONFIGURED"


class ViatorBadRequest(ViatorError):
    status_code = 400
    code = "BAD_REQUEST"
    public_message = "That search couldn't be run. Please adjust the filters and try again."


class ViatorAuthError(ViatorError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"


class ViatorAccessDenied(ViatorError):
    status_code = 403
    code = "ACCESS_DENIED"


class ViatorNotFound(ViatorError):
    status_code = 404
    code = "NOT_FOUND"
    public_message = "That experience or destination could not be found."


class ViatorRateLimited(ViatorError):
    status_code = 429
    code = "RATE_LIMITED"


class ViatorUnavailable(ViatorError):
    """5xx responses, timeouts and network failures."""
    code = "UNAVAILABLE"
